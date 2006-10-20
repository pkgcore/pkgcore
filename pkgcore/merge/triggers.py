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
demandload(globals(), "os "
    "pkgcore.plugin:get_plugin "
    "pkgcore.spawn:spawn ")

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
        return self.__class__

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

        for hook in self._hooks:
            try:
                engine.add_trigger(hook, self)
            except KeyError:
                # unknown hook.
                continue

    def _get_csets(self, csets):
        return [csets[x] for x in self.required_csets]

    def trigger(self, engine, csets):
        raise NotImplementedError(self, 'trigger')

    def __call__(self, engine, csets):
        """execute the trigger"""
        if self.required_csets is None:
            return self.trigger(engine, csets)
        return self.trigger(engine, *self._get_csets(csets))

    def __str__(self):
        return "%s: cset(%s) ftrigger(%s)" % (
            self.__class__, self.required_csets, self.trigger)

    def __repr__(self):
        return "<%s cset=%r @#%x>" % (
            self.__class__.__name__,
            self.required_csets, id(self))


class ldconfig(base):
    
    required_csets = ()
    _engine_types = None
    _hooks = ("post_unmerge", "post_merge")
    _priority = 10
    
    def __init__(self, ld_so_conf_path="etc/ld.so.conf"):
        self.ld_so_conf_path = ld_so_conf_path.lstrip(os.path.sep)

    def trigger(self, engine):
        if engine.offset is None:
            offset = '/'
        else:
            offset = engine.offset
        basedir = os.path.join(offset, os.path.dirname(self.ld_so_conf_path))
        if not os.path.exists(basedir):
            os.mkdir(os.path.join(offset, basedir))
        f = os.path.join(offset, self.ld_so_conf_path)
        if not os.path.exists(f):
            # touch the file basically
            open(f, "w")
        ret = spawn(["/sbin/ldconfig", "-r", offset], fd_pipes={1:1, 2:2})
        if ret != 0:
            raise errors.TriggerWarning(
                "ldconfig returned %i from execution" % ret)


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
