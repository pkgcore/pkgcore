# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
triggers, callables to bind to a step in a MergeEngine to affect changes
"""

__all__ = (
    "base",
    "UNINSTALLING_MODES",
    "INSTALLING_MODES",
    "BaseSystemUnmergeProtection",
    "BinaryDebug",
    "BlockFileType",
    "CommonDirectoryModes",
    "PruneFiles",
    "SavePkg",
    "detect_world_writable",
    "fix_gid_perms",
    "fix_set_bits",
    "fix_uid_perms",
    "ldconfig",
    "merge",
    "unmerge",
    "InfoRegen",
)

from pkgcore.merge import errors, const
from pkgcore.config import ConfigHint
import pkgcore.os_data

from snakeoil.osutils import listdir_files, pjoin, ensure_dirs, normpath
from snakeoil.demandload import demandload
from snakeoil import compatibility

demandload(globals(),
    'os',
    'errno',
    'pkgcore.plugin:get_plugin',
    'pkgcore:spawn',
    'pkgcore.fs.livefs:gen_obj',
    'pkgcore.fs:fs,contents',
    'snakeoil.bash:iter_read_bash',
    're',
    'time',
    'math:floor',
    'pkgcore.package.mutated:MutatedPkg',
    'pkgcore.util:file_type,thread_pool',
    'pkgcore:os_data',
    'pkgcore.operations.observer:threadsafe_repo_observer',
)

UNINSTALLING_MODES = (const.REPLACE_MODE, const.UNINSTALL_MODE)
INSTALLING_MODES = (const.REPLACE_MODE, const.INSTALL_MODE)


class base(object):

    """base trigger class

    :ivar required_csets: If None, all csets are passed in, else it must be a
        sequence, those specific csets are passed in
    :ivar _label: Either None, or a string to use for this triggers label
    :ivar _hook: sequence of hook points to register into
    :ivar priority: range of 0 to 100, order of execution for triggers per hook
    :ivar _engine_types: if None, trigger works for all engine modes, else it's
        limited to that mode, and must be a sequence
    """

    required_csets = None
    _label = None
    _hooks = None
    _engine_types = None
    priority = 50

    suppress_exceptions = True

    pkgcore_config_type = ConfigHint(typename='trigger')

    @property
    def label(self):
        if self._label is not None:
            return self._label
        return str(self.__class__.__name__)

    def register(self, engine):
        """
        register with a MergeEngine
        """
        if self._engine_types is not None and \
            engine.mode not in self._engine_types:
            return

        # ok... so we care about this mode.
        try:
            iter(self._hooks)
        except TypeError:
            # bad monkey...
            raise TypeError("%r: %r: _hooks needs to be a sequence" %
                (self, self._hooks))

        csets = self.get_required_csets(engine.mode)

        for hook in self._hooks:
            try:
                engine.add_trigger(hook, self, csets)
            except KeyError:
                # unknown hook.
                continue

    def get_required_csets(self, mode):
        csets = self.required_csets
        if csets is not None:
            if not isinstance(csets, tuple):
                # has to be a dict.
                csets = csets.get(mode)
        return csets

    def localize(self, engine):
        """
        'localize' a trigger to a specific merge engine process
        mainly used if the trigger comes from configuration
        """
        return self

    @staticmethod
    def _get_csets(required_csets, csets):
        return [csets[x] for x in required_csets]

    def trigger(self, engine, csets):
        raise NotImplementedError(self, 'trigger')

    def __call__(self, engine, csets):
        """execute the trigger"""

        required_csets = self.get_required_csets(engine.mode)

        if required_csets is None:
            return self.trigger(engine, csets)
        return self.trigger(engine, *self._get_csets(required_csets, csets))

    def __str__(self):
        return "%s: cset(%s) ftrigger(%s)" % (
            self.label, self.required_csets, self.trigger)

    def __repr__(self):
        return "<%s cset=%r @#%x>" % (
            self.label,
            self.required_csets, id(self))


class ThreadedTrigger(base):

    def identify_work(self, engine, *csets):
        raise NotImplementedError(self, 'identify_work')

    def _run_job(self, observer, functor, args, kwds):
        try:
            functor(*args, **kwds)
        except compatibility.IGNORED_EXCEPTIONS as e:
            if isinstance(e, KeyboardInterrupt):
                return
            raise
        except Exception as e:
            observer.error("exception occurred in thread: %s",
                e)

    def threading_get_args(self, engine, *csets):
        return ()

    def threading_get_kwargs(self, engine, *csets):
        return {}

    def trigger(self, engine, *csets):
        if not self.threading_setup(engine, *csets):
            return

        observer = engine.observer
        observer = threadsafe_repo_observer(observer)
        args = (observer,) + self.threading_get_args(engine, *csets)
        kwargs = self.threading_get_kwargs(engine, *csets)
        kwargs['threads'] = engine.parallelism

        work = list(self.identify_work(engine, *csets))
        thread_pool.map_async(work, self.thread_trigger, *args, **kwargs)

        self.threading_finish(engine, *csets)

    def threading_setup(self, engine, *csets):
        return True

    def threading_finish(self, engine, *csets):
        pass


class mtime_watcher(object):
    """
    passed a list of locations, return a :obj:`contents.contentsSet` containing
    those that are directories.

    If the location doesn't exist, it's ignored.  If stat_func is os.stat
    and the location is a symlink pointing at a nonexistent location, it's
    ignored.

    Additionally, since this function is used for effectively 'snapshotting'
    related directories, if any mtimes are *now* (fs doesn't do subsecond
    resolution, osx for example), induces a sleep for a second to ensure
    any later re-runs do not get bit by completing within the race window.

    Finally, if any mtime is detected that is in the future, it is reset
    to 'now'.
    """

    def __init__(self):
        self.saved_mtimes = None
        self.locations = None

    def __nonzero__(self):
        return bool(self.saved_mtimes)

    @staticmethod
    def _scan_mtimes(locations, stat_func):
        for x in locations:
            try:
                st = stat_func(x)
            except OSError as oe:
                if not oe.errno == errno.ENOENT:
                    raise
                continue
            obj = gen_obj(x, stat=st)
            if fs.isdir(obj):
                yield obj

    def set_state(self, locations, stat_func=os.stat, forced_past=2):
        """
        set the initial state; will adjust ondisk mtimes as needed
        to avoid race potentials.

        :param locations: sequence, file paths to scan
        :param stat_func: stat'er to use.  defaults to os.stat
        """
        self.locations = locations
        mtimes = list(self._scan_mtimes(locations, stat_func))

        cset = contents.contentsSet(mtimes)
        now = time.time()
        pause_cutoff = floor(now)
        past = float(max(pause_cutoff - forced_past, 0))
        resets = [x for x in mtimes if x.mtime > past]
        for x in resets:
            cset.add(x.change_attributes(mtime=past))
            os.utime(x.location, (past, past))

        self.saved_mtimes = cset

    def check_state(self, locations=None, stat_func=os.stat):
        """
        set the initial state; will adjust ondisk mtimes as needed
        to avoid race potentials.

        :param locations: sequence, file paths to scan; uses the locations
          from the set_state invocation if not supplised.
        :param stat_func: stat'er to use.  defaults to os.stat
        :return: boolean, True if things have changed, False if not.
        """
        if locations is None:
            locations = self.locations

        for x in self.get_changes(locations=locations, stat_func=stat_func):
            return True
        return False

    def get_changes(self, locations=None, stat_func=os.stat):
        """
        generator yielding the fs objs for what has changed.

        :param locations: sequence, file paths to scan; uses the locations
          from the set_state invocation if not supplised.
        :param stat_func: stat'er to use.  defaults to os.stat
        """
        if locations is None:
            locations = self.locations

        for x in self._scan_mtimes(locations, stat_func):
            if x not in self.saved_mtimes or \
                self.saved_mtimes[x].mtime != x.mtime:
                yield x


def update_elf_hints(root):
    return spawn.spawn(["/sbin/ldconfig", "-r", root], fd_pipes={1:1, 2:2})


class ldconfig(base):

    required_csets = ()
    priority = 10
    _engine_types = None
    _hooks = ('pre_merge', 'post_merge', 'pre_unmerge', 'post_unmerge')

    default_ld_path = ['usr/lib', 'usr/lib64', 'usr/lib32', 'lib',
        'lib64', 'lib32']

    pkgcore_config_type = base.pkgcore_config_type.clone(
        types={'ld_so_conf_path':'str'})

    def __init__(self, ld_so_conf_path="etc/ld.so.conf"):
        self.ld_so_conf_path = ld_so_conf_path.lstrip(os.path.sep)
        self.saved_mtimes = mtime_watcher()

    def ld_so_path(self, offset):
        return pjoin(offset, self.ld_so_conf_path)

    def read_ld_so_conf(self, offset):
        fp = self.ld_so_path(offset)

        try:
            l = [x.lstrip(os.path.sep) for x in iter_read_bash(fp)]
        except IOError as oe:
            if oe.errno != errno.ENOENT:
                raise
            self._mk_ld_so_conf(fp)
            # fall back to an educated guess.
            l = self.default_ld_path
        return [pjoin(offset, x) for x in l]

    def _mk_ld_so_conf(self, fp):
        if not ensure_dirs(os.path.dirname(fp), mode=0755, minimal=True):
            raise errors.BlockModification(self,
                "failed creating/setting %s to 0755, root/root for uid/gid" %
                    os.path.basename(fp))
            # touch the file.
        try:
            open(fp, 'w').close()
        except EnvironmentError as e:
            compatibility.raise_from(errors.BlockModification(self, e))

    def trigger(self, engine):
        locations = self.read_ld_so_conf(engine.offset)
        if engine.phase.startswith('pre_'):
            self.saved_mtimes.set_state(locations)
            return

        # always invoke regen; ld.so.conf can have source/include statements,
        # and modern ldconfig maintains a cache that renders this very, very fast.
        self.regen(engine)

    def regen(self, engine):
        ret = update_elf_hints(engine.offset)
        if ret != 0:
            engine.observer.warn("ldconfig returned %i from execution" % (ret,))


class InfoRegen(base):

    required_csets = ()

    # could implement this to look at csets, and do incremental removal and
    # addition; doesn't seem worth while though for the additional complexity

    _hooks = ('pre_merge', 'post_merge', 'pre_unmerge', 'post_unmerge')
    _engine_types = None
    _label = "gnu info regen"

    locations = ('/usr/share/info',)

    def __init__(self):
        self.saved_mtimes = mtime_watcher()

    def get_binary_path(self):
        try:
            return spawn.find_binary('install-info')
        except spawn.CommandNotFound:
            # swallow it.
            return None

    def trigger(self, engine):
        bin_path = self.get_binary_path()
        if bin_path is None:
            return

        offset = engine.offset

        locs = [pjoin(offset, x.lstrip(os.path.sep)) for x in self.locations]

        if engine.phase.startswith('pre_'):
            self.saved_mtimes.set_state(locs)
            return
        elif engine.phase == 'post_merge' and \
            engine.mode == const.REPLACE_MODE:
            # skip post_merge for replace.
            # we catch it on unmerge...
            return

        regens = set(x.location for x in self.saved_mtimes.get_changes(locs))
        # force regeneration of any directory lacking the info index.
        regens.update(x for x in locs if not os.path.isfile(pjoin(x, 'dir')))

        bad = []
        for x in regens:
            bad.extend(self.regen(bin_path, x))

        if bad and engine.observer is not None:
            engine.observer.warn("bad info files: %r" % sorted(bad))

    def should_skip_directory(self, basepath, files):
        return False

    def regen(self, binary, basepath):
        ignores = ("dir", "dir.old")
        try:
            files = listdir_files(basepath)
        except OSError as oe:
            if oe.errno == errno.ENOENT:
                return
            raise

        if self.should_skip_directory(basepath, files):
            return

        # wipe old indexes.
        for x in set(ignores).intersection(files):
            os.remove(pjoin(basepath, x))

        index = pjoin(basepath, 'dir')
        for x in files:
            if x in ignores or x.startswith("."):
                continue

            ret, data = spawn.spawn_get_output(
                [binary, '--quiet', pjoin(basepath, x),
                    '--dir-file', index],
                collect_fds=(1,2), split_lines=False)

            if not data or "already exists" in data or \
                "warning: no info dir entry" in data:
                continue
            yield pjoin(basepath, x)


class merge(base):

    required_csets = ('install',)
    _engine_types = INSTALLING_MODES
    _hooks = ('merge',)

    suppress_exceptions = False

    def trigger(self, engine, merging_cset):
        op = get_plugin('fs_ops.merge_contents')
        return op(merging_cset, callback=engine.observer.installing_fs_obj)


class unmerge(base):

    required_csets = ('uninstall',)
    _engine_types = UNINSTALLING_MODES
    _hooks = ('unmerge',)

    suppress_exceptions = False

    def trigger(self, engine, unmerging_cset):
        op = get_plugin('fs_ops.unmerge_contents')
        return op(unmerging_cset, callback=engine.observer.removing_fs_obj)


class BaseSystemUnmergeProtection(base):

    required_csets = ('uninstall',)
    priority = -100
    _engine_types = UNINSTALLING_MODES
    _hooks = ('unmerge',)

    suppress_exceptions = False

    _preserve_sequence = ('/usr', '/usr/lib', '/usr/lib64', '/usr/lib32',
        '/usr/bin', '/usr/sbin', '/bin', '/sbin', '/lib', '/lib32', '/lib64',
        '/etc', '/var', '/home', '/root')

    pkgcore_config_type = base.pkgcore_config_type.clone(types=
        {"preserve_sequence":"list"})

    def __init__(self, preserve_sequence=None):
        if preserve_sequence is None:
            preserve_sequence = self._preserve_sequence
        self._block = tuple(x.lstrip('/') for x in preserve_sequence)

    def trigger(self, engine, uninstall):
        uninstall.difference_update(pjoin(engine.offset, x) for x in self._block)
        return True


class fix_uid_perms(base):

    required_csets = ('new_cset',)
    _hooks = ('pre_merge',)
    _engine_types = INSTALLING_MODES

    def __init__(self, uid=pkgcore.os_data.portage_uid,
                 replacement=pkgcore.os_data.root_uid):
        base.__init__(self)
        self.bad_uid = uid
        self.good_uid = replacement

    def trigger(self, engine, cset):
        good = self.good_uid
        bad = self.bad_uid

        cset.update(x.change_attributes(uid=good)
            for x in cset if x.uid == bad)


class fix_gid_perms(base):

    required_csets = ('new_cset',)
    _hooks = ('pre_merge',)
    _engine_types = INSTALLING_MODES

    def __init__(self, gid=pkgcore.os_data.portage_gid,
                 replacement=pkgcore.os_data.root_gid):
        base.__init__(self)
        self.bad_gid = gid
        self.good_gid = replacement

    def trigger(self, engine, cset):
        good = self.good_gid
        bad = self.bad_gid

        cset.update(x.change_attributes(gid=good)
            for x in cset if x.gid == bad)


class fix_set_bits(base):

    required_csets = ('new_cset',)
    _hooks = ('pre_merge',)
    _engine_types = INSTALLING_MODES

    def trigger(self, engine, cset):
        reporter = engine.observer
        # if s(uid|gid) *and* world writable...
        l = [x for x in cset.iterlinks(True) if
            (x.mode & 06000) and (x.mode & 0002)]

        if reporter is not None:
            for x in l:
                if x.mode & 04000:
                    reporter.warn(
                        "correcting unsafe world writable SetGID: %s" %
                            (x.location,))
                else:
                    reporter.warn(
                        "correcting unsafe world writable SetUID: %s" %
                            (x.location,))

        if l:
            # wipe setgid/setuid
            cset.update(x.change_attributes(mode=x.mode & ~06002) for x in l)


class detect_world_writable(base):

    required_csets = ('new_cset',)
    _hooks = ('pre_merge',)
    _engine_types = INSTALLING_MODES

    def __init__(self, fix_perms=False):
        base.__init__(self)
        self.fix_perms = fix_perms

    def trigger(self, engine, cset):
        if not engine.observer and not self.fix_perms:
            return

        reporter = engine.observer

        l = [x for x in cset.iterlinks(True) if x.mode & 0002]
        if reporter is not None:
            for x in l:
                reporter.warn("world writable file: %s" % x.location)
        if self.fix_perms:
            cset.update(x.change_attributes(mode=x.mode & ~0002) for x in l)


class PruneFiles(base):

    required_csets = ('new_cset',)
    _hooks = ('pre_merge',)
    _engine_types = INSTALLING_MODES

    pkgcore_config_type = None

    def __init__(self, sentinel_func):
        """
        :param sentinel_func: callable accepting a fsBase entry, returns
        True if the entry should be removed, False otherwise
        """
        base.__init__(self)
        self.sentinel = sentinel_func

    def trigger(self, engine, cset):
        removal = filter(self.sentinel, cset)
        if engine.observer:
            for x in removal:
                engine.observer.info("pruning: %s" % x.location)
        cset.difference_update(removal)


class CommonDirectoryModes(base):

    required_csets = ('new_cset',)
    _hooks = ('pre_merge',)
    _engine_types = INSTALLING_MODES

    directories = [pjoin('/usr', x) for x in ('.', 'lib', 'lib64', 'lib32',
        'bin', 'sbin', 'local')]
    directories.extend(pjoin('/usr/share', x) for x in ('.', 'man', 'info'))
    directories.extend('/usr/share/man/man%i' % x for x in xrange(1, 10))
    directories.extend(['/lib', '/lib32', '/lib64', '/etc', '/bin', '/sbin',
        '/var'])
    directories = frozenset(map(normpath, directories))
    if not compatibility.is_py3k:
        del x

    def trigger(self, engine, cset):
        r = engine.observer
        if not r:
            return
        for x in cset.iterdirs():
            if x.location not in self.directories:
                continue
            if x.mode != 0755:
                r.warn('%s path has mode %s, should be 0755' %
                    (x.location, oct(x.mode)))


class BlockFileType(base):

    required_csets = ('new_cset',)
    _hooks = ('pre_merge',)
    _engine_types = INSTALLING_MODES

    def __init__(self, bad_regex, regex_to_check=None, fatal=True):
        self.bad_regex, self.filter_regex = bad_regex, regex_to_check
        self.fatal = fatal

    def trigger(self, engine, cset):
        file_typer = file_type.file_identifier()

        if self.filter_regex is None:
            filter_re = lambda x:True
        else:
            filter_re = re.compile(self.filter_regex).match
        bad_pat = re.compile(self.bad_regex).match

        bad_files = []
        # this won't play perfectly w/ binpkgs
        for x in (x for x in cset.iterfiles() if filter_re(x.location)):
            if bad_pat(file_typer(x.data)):
                engine.observer.warn("disallowed file type: %r" % x)
                bad_files.append(x)
        if self.fatal and bad_files:
            raise errors.BlockModification(self,
                "blacklisted filetypes were encountered- pattern %r matched files: %r" %
                    (self.bad_regex, sorted(bad_files)))


class SavePkg(base):

    required_csets = ('raw_new_cset',)
    priority = 1000
    _hooks = ('sanity_check',)
    _engine_types = INSTALLING_MODES

    _copy_source = 'new'

    pkgcore_config_type = base.pkgcore_config_type.clone(
        types={'target_repo':'ref:repo','pristine':'bool',
            'skip_if_source':'bool'},
        required=['target_repo'])

    def __init__(self, target_repo, pristine=True, skip_if_source=True):
        if not pristine:
            self._hooks = ('pre_merge',)
            self.required_csets = ('install',)
        self.skip_if_source = skip_if_source
        self.target_repo = target_repo

    def trigger(self, engine, cset):
        pkg = getattr(engine, self._copy_source)
        if self.skip_if_source and getattr(pkg, 'repo') == self.target_repo:
            return

        old_pkg = self.target_repo.match(pkg.versioned_atom)
        wrapped_pkg = MutatedPkg(pkg, {'contents':cset})
        if old_pkg:
            txt = 'replacing'
            op = self.target_repo.operations.replace(*(old_pkg + [wrapped_pkg]))
        else:
            txt = 'installing'
            op = self.target_repo.operations.install(wrapped_pkg)
        engine.observer.info("%s %s to %s" %
            (txt, pkg, self.target_repo))
        op.finish()


class SavePkgIfInPkgset(SavePkg):

    d = SavePkg.pkgcore_config_type.types.copy()
    d['pkgset'] = 'ref:pkgset'
    pkgcore_config_type = SavePkg.pkgcore_config_type.clone(types=d,
        required=['target_repo', 'pkgset'])
    del d

    def __init__(self, target_repo, pkgset, pristine=True,
                 skip_if_source=True):
        SavePkg.__init__(self, target_repo, pristine=pristine,
            skip_if_source=skip_if_source)
        self.pkgset = pkgset

    def trigger(self, engine, cset):
        pkg = getattr(engine, self._copy_source)
        if any(x.match(pkg) for x in self.pkgset):
            return SavePkg.trigger(self, engine, cset)


class SavePkgUnmerging(SavePkg):
    required_csets = ('old_cset',)
    _engine_types = UNINSTALLING_MODES
    _copy_source = 'old'

    pkgcore_config_type = base.pkgcore_config_type.clone(
        types={'target_repo':'ref:repo'})

    def __init__(self, target_repo):
        self.target_repo = target_repo


class SavePkgUnmergingIfInPkgset(SavePkgUnmerging):

    pkgcore_config_type = base.pkgcore_config_type.clone(
        types={'target_repo':'ref:repo', 'pkgset':'ref:pkgset'},
        required=['target_repo', 'pkgset'])

    def __init__(self, target_repo, pkgset, pristine=True):
        SavePkgUnmerging.__init__(self, target_repo, pristine=pristine)
        self.pkgset = pkgset

    def trigger(self, engine, cset):
        pkg = getattr(engine, self._copy_source)
        if any(x.match(pkg) for x in self.pkgset):
            return SavePkgUnmerging.trigger(self, engine, cset)


class BinaryDebug(ThreadedTrigger):

    required_csets = ('install',)
    _engine_types = INSTALLING_MODES

    _hooks = ('pre_merge',)

    default_strip_flags = ('--strip-unneeded', '-R', '.comment')
    elf_regex = '(^| )ELF +(\d+-bit )'

    pkgcore_config_type = base.pkgcore_config_type.clone(
        types={"strip_binary":"str", "objcopy_binary":"str"})

    def __init__(self, mode='split', strip_binary=None, objcopy_binary=None,
                 extra_strip_flags=(), debug_storage='/usr/lib/debug/', compress=False):
        self.mode = mode = mode.lower()
        if mode not in ('split', 'strip'):
            raise TypeError("mode %r is unknown; must be either split "
                "or strip")
        self.thread_trigger = getattr(self, '_%s' % mode)
        self.threading_setup = getattr(self, '_%s_setup' % mode)
        self.threading_finish = getattr(self, '_%s_finish' % mode)

        self._strip_binary = strip_binary
        self._objcopy_binary = objcopy_binary
        self._strip_flags = list(self.default_strip_flags)
        self._extra_strip_flags = list(extra_strip_flags)
        self._debug_storage = debug_storage
        self._compress = compress

    def _initialize_paths(self, pkg):
        for x in ("strip", "objcopy"):
            obj = getattr(self, "_%s_binary" % x)
            if obj is None:
                try:
                    obj = spawn.find_binary("%s-%s" % (pkg.chost, x))
                except spawn.CommandNotFound:
                    obj = spawn.find_binary(x)
            setattr(self, '%s_binary' % x, obj)

    def _strip_fsobj(self, fs_obj, ftype, reporter, quiet=False):
        args = self._strip_flags
        if "executable" in ftype or "shared object" in ftype:
            args += self._extra_strip_flags
        elif "current ar archive" in ftype:
            args = ['-g']
        if not quiet:
            reporter.info("stripping: %s %s" % (fs_obj, ' '.join(args)))
        ret = spawn.spawn([self.strip_binary] + args +
            [fs_obj.data.path])
        if ret != 0:
            reporter.warn("stripping %s, type %s failed" % (fs_obj, ftype))
        # need to update chksums here...
        return fs_obj

    def identify_work(self, engine, cset):
        file_typer = file_type.file_identifier()
        regex_f = re.compile(self.elf_regex).match
        engine.observer.debug("starting binarydebug filetype scan")
        for fs_objs in cset.inode_map().itervalues():
            fs_obj = fs_objs[0]
            ftype = file_typer(fs_obj.data)
            if regex_f(ftype):
                yield fs_objs, ftype
        engine.observer.debug("completed binarydebug scan")

    def threading_get_args(self, engine, cset):
        return (engine, cset)

    def _strip_setup(self, engine, cset):
        if 'strip' in getattr(engine.new, 'restrict', ()):
            engine.observer.info("stripping disabled for %s" % engine.new)
            return False
        self._initialize_paths(engine.new)
        self._modified = set()
        return True

    def _strip(self, iterable, observer, engine, cset):
        for fs_objs, ftype in iterable:
            # strip the first hardlink; then update the rest with the
            # new objects data.
            stripped = self._strip_fsobj(fs_objs[0], ftype, observer)
            self._modified.add(stripped)
            self._modified.update(stripped.change_attributes(location=fs_obj.data.path)
                for fs_obj in fs_objs[1:])

    def _strip_finish(self, engine, cset):
        if hasattr(self, '_modified'):
            cset.update(self._modified)
            del self._modified

    def _split_setup(self, engine, cset):
        skip = frozenset(['strip', 'splitdebug']).intersection(getattr(engine.new, 'restrict', ()))
        skip = bool(skip)
        if not skip:
            for fs_obj in cset:
                if fs_obj.basename.endswith(".debug"):
                    skip = True
                    break
        if skip:
            engine.observer.info("splitdebug disabled for %s, "
                "skipping splitdebug" % engine.new)
            return False

        self._initialize_paths(engine.new)
        self._modified = contents.contentsSet()
        return True

    def _split(self, iterable, observer, engine, cset):
        debug_store = pjoin(engine.offset, self._debug_storage.lstrip('/'))

        objcopy_args = [self.objcopy_binary, '--only-keep-debug']
        if self._compress:
            objcopy_args.append('--compress-debug-sections')

        for fs_objs, ftype in iterable:
            if 'ar archive' in ftype:
                continue
            if 'relocatable' in ftype:
                if not any(x.basename.endswith(".ko") for x in fs_objs):
                    continue
            fs_obj = fs_objs[0]
            debug_loc = pjoin(debug_store, fs_obj.location.lstrip('/') + ".debug")
            if debug_loc in cset:
                continue
            fpath = fs_obj.data.path
            debug_ondisk = pjoin(os.path.dirname(fpath),
                os.path.basename(fpath) + ".debug")

            # note that we tell the UI the final pathway- not the intermediate one.
            observer.info("splitdebug'ing %s into %s" %
                (fs_obj.location, debug_loc))

            ret = spawn.spawn(objcopy_args + [fpath, debug_ondisk])
            if ret != 0:
                observer.warn("splitdebug'ing %s failed w/ exitcode %s" %
                    (fs_obj.location, ret))
                continue

            # note that the given pathway to the debug file /must/ be relative to ${D};
            # it must exist at the time of invocation.
            ret = spawn.spawn([self.objcopy_binary,
                '--add-gnu-debuglink', debug_ondisk, fpath])
            if ret != 0:
                observer.warn("splitdebug created debug file %r, but "
                    "failed adding links to %r (%r)" % (debug_ondisk, fpath, ret))
                observer.debug("failed splitdebug command was %r",
                    (self.objcopy_binary, '--add-gnu-debuglink', debug_ondisk, fpath))
                continue


            debug_obj = gen_obj(debug_loc, real_location=debug_ondisk,
                uid=os_data.root_uid, gid=os_data.root_gid)

            stripped_fsobj = self._strip_fsobj(fs_obj, ftype, observer, quiet=True)

            self._modified.add(stripped_fsobj)
            self._modified.add(debug_obj)

            for fs_obj in fs_objs[1:]:
                debug_loc = pjoin(debug_store,
                    fs_obj.location.lstrip('/') + ".debug")
                linked_debug_obj = debug_obj.change_attributes(location=debug_loc)
                observer.info("splitdebug hardlinking %s to %s" %
                    (debug_obj.location, debug_loc))
                self._modified.add(linked_debug_obj)
                self._modified.add(stripped_fsobj.change_attributes(
                    location=fs_obj.location))

    def _split_finish(self, engine, cset):
        if not hasattr(self, '_modified'):
            return
        self._modified.add_missing_directories(mode=0775)
        # add the non directories first.
        cset.update(self._modified.iterdirs(invert=True))
        # punt any intersections, leaving just the new directories.
        self._modified.difference_update(cset)
        cset.update(self._modified)
        del self._modified

