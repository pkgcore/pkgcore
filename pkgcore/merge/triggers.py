# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2
# $Id:$

"""
triggers, callables to bind to a step in a MergeEngine to affect changes
"""

__all__ = [
    "base",
    "trigger",
    "UNINSTALLING_MODES",
    "INSTALLING_MODES"
]

from pkgcore.merge import errors, const
import pkgcore.os_data

from snakeoil.osutils import listdir_files, pjoin, ensure_dirs, normpath
from snakeoil.demandload import demandload
demandload(globals(),
    'os',
    'errno',
    'pkgcore.plugin:get_plugin',
    'pkgcore:spawn',
    'pkgcore.fs.livefs:gen_obj',
    'pkgcore.fs:fs,contents',
    'snakeoil.fileutils:iter_read_bash',
    'time',
    'math:floor',
)

UNINSTALLING_MODES = (const.REPLACE_MODE, const.UNINSTALL_MODE)
INSTALLING_MODES = (const.REPLACE_MODE, const.INSTALL_MODE)


class base(object):

    """base trigger class

    @ivar required_csets: If None, all csets are passed in, else it must be a
        sequence, those specific csets are passed in
    @ivar _label: Either None, or a string to use for this triggers label
    @ivar _hook: sequence of hook points to register into
    @ivar _priority: range of 0 to 100, order of execution for triggers per hook
    @ivar _engine_types: if None, trigger works for all engine modes, else it's
        limited to that mode, and must be a sequence
    """

    required_csets = None
    _label = None
    _hooks = None
    _engine_types = None
    _priority = 50

    @property
    def priority(self):
        return self._priority

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
            i = iter(self._hooks)
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

    def localize(self, mergeengine):
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


class mtime_watcher(object):
    """
    passed a list of locations, return a L{contents.contentsSet} containing
    those that are directories.

    If the location doesn't exist, it's ignored.  If stat_func is os.stat
    and the location is a symlink pointing at a non existant location, it's
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

    def mtime_floats(func):
        def mtime_floats_wrapper(self, *args, **kwargs):
            cur = os.stat_float_times()
            try:
                os.stat_float_times(True)
                return func(self, *args, **kwargs)
            finally:
                os.stat_float_times(cur)
        return mtime_floats_wrapper

    def __nonzero__(self):
        return bool(self.saved_mtimes)

    @staticmethod
    def _scan_mtimes(locations, stat_func):
        for x in locations:
            try:
                st = stat_func(x)
            except OSError, oe:
                if not oe.errno == errno.ENOENT:
                    raise
                continue
            obj = gen_obj(x, stat=st)
            if fs.isdir(obj):
                yield obj

    @mtime_floats
    def set_state(self, locations, stat_func=os.stat, forced_past=2):
        """
        set the initial state; will adjust ondisk mtimes as needed
        to avoid race potentials.

        @param locations: sequence, file paths to scan
        @param stat_func: stat'er to use.  defaults to os.stat
        """
        self.locations = locations
        mtimes = list(self._scan_mtimes(locations, stat_func))

        cset = contents.contentsSet(mtimes)
        now = time.time()
        pause_cutoff = floor(now)
        past = max(pause_cutoff - forced_past, 0)
        resets = [x for x in mtimes if x.mtime > past]
        for x in resets:
            cset.add(x.change_attributes(mtime=past))
            os.utime(x.location, (past, past))

        self.saved_mtimes = cset

    @mtime_floats
    def check_state(self, locations=None, stat_func=os.stat):
        """
        set the initial state; will adjust ondisk mtimes as needed
        to avoid race potentials.

        @param locations: sequence, file paths to scan; uses the locations
          from the set_state invocation if not supplised.
        @param stat_func: stat'er to use.  defaults to os.stat
        @return: boolean, True if things have changed, False if not.
        """
        if locations is None:
            locations = self.locations

        for x in self.get_changes(locations=locations, stat_func=stat_func):
            return True
        return False

    @mtime_floats
    def get_changes(self, locations=None, stat_func=os.stat):
        """
        generator yielding the fs objs for what has changed.

        @param locations: sequence, file paths to scan; uses the locations
          from the set_state invocation if not supplised.
        @param stat_func: stat'er to use.  defaults to os.stat
        """
        if locations is None:
            locations = self.locations

        for x in self._scan_mtimes(locations, stat_func):
            if x not in self.saved_mtimes or \
                self.saved_mtimes[x].mtime != x.mtime:
                yield x


class ldconfig(base):

    required_csets = ()
    _engine_types = None
    _hooks = ('pre_merge', 'post_merge', 'pre_unmerge', 'post_unmerge')
    _priority = 10

    default_ld_path = ['usr/lib', 'usr/lib64', 'usr/lib32', 'lib',
        'lib64', 'lib32']

    def __init__(self, ld_so_conf_path="etc/ld.so.conf"):
        self.ld_so_conf_path = ld_so_conf_path.lstrip(os.path.sep)
        self.saved_mtimes = mtime_watcher()

    def ld_so_path(self, offset):
        return pjoin(offset, self.ld_so_conf_path)

    def read_ld_so_conf(self, offset):
        fp = self.ld_so_path(offset)

        try:
            l = [x.lstrip(os.path.sep) for x in iter_read_bash(fp)]
        except IOError, oe:
            if oe.errno != errno.ENOENT:
                raise
            self._mk_ld_so_conf(fp)
            # fall back to an edjucated guess.
            l = self.default_ld_path
        return [pjoin(offset, x) for x in l]

    def _mk_ld_so_conf(self, fp):
        if not ensure_dirs(os.path.dirname(fp), mode=0755, minimal=True):
            raise errors.BlockModification(self,
                "failed creating/setting %s to 0755, root/root for uid/gid" %
                    os.path.basename(fp))
            # touch the file.
        try:
            open(fp, 'w')
        except (IOError, OSError), e:
            raise errors.BlockModification(self, e)

    def trigger(self, engine):
        locations = self.read_ld_so_conf(engine.offset)
        if engine.phase.startswith('pre_'):
            self.saved_mtimes.set_state(locations)
            return

        if self.saved_mtimes.check_state(locations):
            self.regen(engine.offset)

    def regen(self, offset):
        ret = spawn.spawn(["/sbin/ldconfig", "-r", offset], fd_pipes={1:1, 2:2})
        if ret != 0:
            raise errors.TriggerWarning(self,
                "ldconfig returned %i from execution" % ret)


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

    def regen(self, binary, basepath):
        ignores = ("dir", "dir.old")
        try:
            files = listdir_files(basepath)
        except OSError, oe:
            if oe.errno == errno.ENOENT:
                return
            raise

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

    def trigger(self, engine, merging_cset):
        op = get_plugin('fs_ops.merge_contents')
        return op(merging_cset, callback=engine.observer.installing_fs_obj)


class unmerge(base):

    required_csets = ('uninstall',)
    _engine_types = UNINSTALLING_MODES
    _hooks = ('unmerge',)

    def trigger(self, engine, unmerging_cset):
        op = get_plugin('fs_ops.unmerge_contents')
        return op(unmerging_cset, callback=engine.observer.removing_fs_obj)


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
                        "correcing unsafe world writable SetGID: %s",
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

    def __init__(self, sentinel_func):
        """
        @param sentinel_func: callable accepting a fsBase entry, returns
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
