# Copyright: 2006 Brian Harring <ferringb@gmail.com>
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
from pkgcore.util.demandload import demandload
from pkgcore.util.osutils import listdir_files, join as pjoin
demandload(globals(), "os errno "
    "pkgcore.plugin:get_plugin "
    "pkgcore:spawn "
    "pkgcore.fs.livefs:gen_obj "
    "pkgcore.fs:fs,contents "
    "pkgcore.util.file:iter_read_bash "
    )

UNINSTALLING_MODES = (const.REPLACE_MODE, const.UNINSTALL_MODE)
INSTALLING_MODES = (const.REPLACE_MODE, const.INSTALL_MODE)


class base(object):

    """base trigger class

    @ivar required_csets: If None, all csets are passed in, else it must be a
        sequence, those specific csets are passed in
    @ivar _label: Either None, or a string to use for this triggers label
    @ivar _hook: sequence of hook points to register into
    @ivar _priority: range of 0 to 100, order of execution for triggers per hook.
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
                csets = csets.get(mode, None)
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


def get_dir_mtimes(locations):
    mtimes = []
    for x in locations:
        try:
            # we force our own os.stat, instead of genobjs lstat
            st = os.stat(x)
        except OSError, oe:
            if not oe.errno == errno.ENOENT:
                raise
            del oe
            continue
        obj = gen_obj(x, stat=st)
        if fs.isdir(obj):
            mtimes.append(obj)
    return contents.contentsSet(mtimes)


class ldconfig(base):

    required_csets = ()
    _engine_types = None
    _hooks = ('pre_merge', 'post_merge', 'pre_unmerge', 'post_unmerge')
    _priority = 10

    def __init__(self, ld_so_conf_path="etc/ld.so.conf"):
        self.ld_so_conf_path = ld_so_conf_path.lstrip(os.path.sep)
        self.saved_mtimes = contents.contentsSet()

    def ld_so_path(self, offset):
        return pjoin(offset, self.ld_so_conf_path)

    def read_ld_so_conf(self, offset):
        fp = self.ld_so_path(offset)
        basedir = os.path.dirname(fp)
        if not os.path.exists(basedir):
            os.mkdir(basedir)

        try:
            l = [x.lstrip(os.path.sep) for x in iter_read_bash(fp)]
        except OSError, oe:
            if oe.errno != errno.ENOENT:
                raise
            # touch the file.
            open(fp, 'w')
            # fall back to an edjucated guess.
            l = ['usr/lib', 'usr/lib64', 'usr/lib32', 'lib', 'lib64', 'lib32']
        return [pjoin(offset, x) for x in l]

    def trigger(self, engine):
        self.offset = engine.offset
        if engine.offset is None:
            self.offset = '/'

        if engine.phase.startswith('pre_'):
            self.saved_mtimes = get_dir_mtimes(
                self.read_ld_so_conf(engine.offset))
            return

        new_mtimes = get_dir_mtimes(self.read_ld_so_conf(engine.offset))

        for x in new_mtimes:
            if x not in self.saved_mtimes or \
                self.saved_mtimes[x].mtime != x.mtime:
                break
        else:
            if not new_mtimes.difference(self.saved_mtimes):
                return
        self.regen(engine.offset)
        self.saved_mtimes = new_mtimes

    def regen(self, offset):
        ret = spawn.spawn(["/sbin/ldconfig", "-r", offset], fd_pipes={1:1, 2:2})
        if ret != 0:
            raise errors.TriggerWarning(
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
        self.saved_mtimes = contents.contentsSet()

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

        if engine.phase.startswith('pre_'):
            self.saved_mtimes = get_dir_mtimes(self.locations)
            return
        elif engine.phase == 'post_merge' and \
            engine.mode == const.REPLACE_MODE:
            # skip post_merge for replace.
            # we catch it on unmerge...
            return
        new_mtimes = get_dir_mtimes(self.locations)

        for x in self.saved_mtimes.difference(new_mtimes):
            # locations to wipe the dir file from.
            try:
                os.remove(x)
            except OSError:
                # don't care...
                continue

        # wiped the oldies.  now force updates.
        bad = []
        for x in new_mtimes:
            if x not in self.saved_mtimes or \
                self.saved_mtimes[x].mtime != x.mtime:
                bad.extend(self.regen(bin_path, x.location))
        self.saved_mtimes = new_mtimes
        if bad and engine.observer is not None:
            engine.observer.warn("bad info files: %r" % sorted(bad))

    def regen(self, binary, basepath):
        ignores = ("dir", "dir.old")
        files = listdir_files(basepath)

        # wipe old indexes.
        for x in set(ignores).difference(files):
            os.remove(pjoin(basepath, x))

        index = pjoin(basepath, 'dir')
        for x in files:
            if x in ignores:
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
    _hooks = ('sanity_check',)
    _engine_types = INSTALLING_MODES

    def __init__(self, uid=pkgcore.os_data.portage_uid,
        replacement=pkgcore.os_data.root_uid):

        base.__init__(self)
        self.bad_uid = uid
        self.good_uid = replacement

    def trigger(self, engine, cset):
        good = self.good_uid
        bad = self.bad_uid

        # do it as a list, since we're mutating the set
        resets = [x.change_attributes(uid=good)
            for x in cset if x.uid == bad]

        cset.update(resets)


class fix_gid_perms(base):

    required_csets = ('new_cset',)
    _hooks = ('sanity_check',)
    _engine_types = INSTALLING_MODES

    def __init__(self, gid=pkgcore.os_data.portage_gid,
        replacement=pkgcore.os_data.root_gid):

        base.__init__(self)
        self.bad_gid = gid
        self.good_gid = replacement

    def trigger(self, engine, cset):
        good = self.good_gid
        bad = self.bad_gid

        # do it as a list, since we're mutating the set
        resets = [x.change_attributes(gid=good)
            for x in cset if x.gid == bad]

        cset.update(resets)


class fix_set_bits(base):

    required_csets = ('new_cset',)
    _hooks = ('sanity_check',)
    _engine_types = INSTALLING_MODES

    def trigger(self, engine, cset):
        reporter = engine.reporter
        l = []
        for x in cset:
            # check for either sgid or suid, then write.
            if (x.mode & 06000) and (x.mode & 0002):
                l.append(x)

        if reporter is not None:
            for x in l:
                if x.mode & 04000:
                    reporter.error(
                        "UNSAFE world writable SetGID: %s", (x.location,))
                else:
                    reporter.error(
                        "UNSAFE world writable SetUID: %s" % (x.location,))

        if l:
            # filters the 02, for those who aren't accustomed to
            # screwing with mode.
            cset.update(x.change_attributes(mode=x.mode & ~02) for x in l)


class detect_world_writable(base):

    required_csets = ('new_cset',)
    _hooks = ('sanity_check',)
    _engine_types = INSTALLING_MODES

    def __init__(self, fix_perms=False):
        base.__init__(self)
        self.fix_perms = fix_perms

    def trigger(self, engine, cset):
        if not engine.reporter and not self.fix_perms:
            return

        reporter = engine.reporter

        l = []
        for x in cset:
            if x.mode & 0001:
                l.append(x)
        if reporter is not None:
            for x in l:
                reporter.warn("world writable file: %s", (x.location,))
        if fix_perms:
            cset.update(x.change_attributes(mode=x.mode & ~01) for x in l)


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
        f = self.sentinel
        removal = [x for x in cset if f(x)]
        noise = engine.reporter
        if not noise:
            cset.difference_update(removal)
        else:
            for x in removal:
                noise.info("pruning: %s", (x.location,))
                cset.discard(x)
