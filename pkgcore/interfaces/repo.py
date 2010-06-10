# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
repository modifications (installing, removing, replacing)
"""

from snakeoil.dependant_methods import ForcedDepends
from snakeoil.weakrefs import WeakRefFinalizer
from snakeoil.demandload import demandload
from snakeoil.currying import partial, post_curry
demandload(globals(), "pkgcore.log:logger",
    "pkgcore.interfaces:observer@observer_mod",
    "pkgcore:sync",
    "pkgcore.merge.engine:MergeEngine",
    "pkgcore.merge:errors@merge_errors")


class fake_lock(object):
    def __init__(self):
        pass

    acquire_write_lock = acquire_read_lock = __init__
    release_read_lock = release_write_lock = __init__


class base(object):
    __metaclass__ = ForcedDepends

    stage_depends = {}

class finalizer_base(WeakRefFinalizer, ForcedDepends):

    pass

class Failure(Exception):
    pass


class nonlivefs_base(base):

    stage_depends = {'finish': '_notify_repo', '_notify_repo': 'modify_repo',
        'modify_repo':'start'}

    def __init__(self, repo, observer):
        self.repo = repo
        self.underway = False
        self.observer = observer
        try:
            self.lock = getattr(repo, "lock")
        except AttributeError:
            raise
        if self.lock is None:
            self.lock = fake_lock()

    def start(self):
        self.underway = True
        self.lock.acquire_write_lock()
        return True

    def modify_repo(self):
        raise NotImplementedError(self, 'modify_repo')

    def _notify_repo(self):
        raise NotImplementedError(self, '_notify_repo')

    def finish(self):
        self._notify_repo()
        self.lock.release_write_lock()
        self.underway = False
        return True


class nonlivefs_install(nonlivefs_base):

    def __init__(self, repo, pkg, observer):
        nonlivefs_base.__init__(self, repo, observer)
        self.new_pkg = pkg

    def _notify_repo(self):
        self.repo.notify_add_package(self.new_pkg)


class nonlivefs_uninstall(nonlivefs_base):

    def __init__(self, repo, pkg, observer):
        nonlivefs_base.__init__(self, repo, observer)
        self.old_pkg = pkg

    def _notify_repo(self):
        self.repo.notify_remove_package(self.old_pkg)


class nonlivefs_replace(nonlivefs_install, nonlivefs_uninstall):

    def __init__(self, repo, oldpkg, newpkg, observer):
        # yes there is duplicate initialization here.
        nonlivefs_uninstall.__init__(self, repo, oldpkg, observer)
        nonlivefs_install.__init__(self, repo, newpkg, observer)

    def _notify_repo(self):
        nonlivefs_uninstall._notify_repo(self)
        nonlivefs_install._notify_repo(self)


class livefs_base(base):

    __metaclass__ = finalizer_base

    stage_hooks = []

    def __init__(self, repo, observer, triggers, offset):
        self.repo = repo
        self.underway = False
        self.offset = offset
        self.observer = observer
        self.triggers = triggers
        self.get_op()
        self.lock = getattr(repo, "lock")
        if self.lock is None:
            self.lock = fake_lock()

    def _add_triggers(self, engine):
        for trigger in self.triggers:
            trigger.register(engine)

    def customize_engine(self, engine):
        pass

    def _get_format_op_args_kwds(self):
        return (), {}

    def start(self, engine):
        self.me = engine
        self.underway = True
        self.lock.acquire_write_lock()
        self.me.sanity_check()
        return True

    def finish(self):
        """finish the transaction"""
        self.me.final()
        self._notify_repo()
        self.lock.release_write_lock()
        self.underway = False
        return True

    def _modify_repo_cache(self):
        raise NotImplementedError

    def __del__(self):
        if getattr(self, 'underway', False):
            print "warning: %s merge was underway, but wasn't completed"
            self.lock.release_write_lock()


class livefs_install(livefs_base):

    """base interface for installing a pkg into a livefs repo.

    repositories should override as needed.
    """

    stage_depends = {
        "finish":"merge_metadata", "merge_metadata":"postinst",
        "postinst":"transfer", "transfer":"preinst", "preinst":"start"}
    stage_hooks = ["merge_metadata", "postinst", "preinst", "transfer"]
    install_op_name = "_repo_install_op"
    engine_kls = staticmethod(MergeEngine.install)

    def __init__(self, repo, pkg, observer, triggers, offset):
        self.new_pkg = pkg
        livefs_base.__init__(self, repo, observer, triggers, offset)

    install_get_format_op_args_kwds = livefs_base._get_format_op_args_kwds

    def get_op(self):
        op_args, op_kwds = self.install_get_format_op_args_kwds()
        op_kwds["observer"] = self.observer
        self.install_op = getattr(self.new_pkg,
            self.install_op_name)(*op_args, **op_kwds)

    def start(self):
        """start the install transaction"""
        engine = self.engine_kls(self.new_pkg, offset=self.offset,
            observer=self.observer)
        self.new_pkg.add_format_triggers(self, self.install_op, engine)
        self._add_triggers(engine)
        self.customize_engine(engine)
        return livefs_base.start(self, engine)

    def preinst(self):
        """execute any pre-transfer steps required"""
        return self.install_op.preinst()

    def transfer(self):
        """execute the actual transfer"""
        for merge_phase in (self.me.pre_merge, self.me.merge,
            self.me.post_merge):
            try:
                merge_phase()
            except merge_errors.NonFatalModification, e:
                print "warning caught: %s" % e
        return True

    def _notify_repo(self):
        self.repo.notify_add_package(self.new_pkg)

    def postinst(self):
        """execute any post-transfer steps required"""
        return self.install_op.postinst()

    def merge_metadata(self):
        """merge pkg metadata to the repository.  Must be overrided"""
        raise NotImplementedError

    def finish(self):
        ret = self.install_op.finalize()
        if not ret:
            logger.warn("ignoring unexpected result from install finalize- "
                "%r" % ret)
        return livefs_base.finish(self)


class livefs_uninstall(livefs_base):

    """base interface for uninstalling a pkg from a livefs repo.

    Repositories should override as needed.
    """

    stage_depends = {
        "finish":"unmerge_metadata", "unmerge_metadata":"postrm",
        "postrm":"remove", "remove":"prerm", "prerm":"start"}
    stage_hooks = ["merge_metadata", "postrm", "prerm", "remove"]
    uninstall_op_name = "_repo_uninstall_op"
    engine_kls = staticmethod(MergeEngine.uninstall)

    def __init__(self, repo, pkg, observer, triggers, offset):
        self.old_pkg = pkg
        livefs_base.__init__(self, repo, observer, triggers, offset)

    uninstall_get_format_op_args_kwds = livefs_base._get_format_op_args_kwds

    def get_op(self):
        op_args, op_kwds = self.uninstall_get_format_op_args_kwds()
        op_kwds["observer"] = self.observer
        self.uninstall_op = getattr(self.old_pkg,
            self.uninstall_op_name)(*op_args, **op_kwds)

    def start(self):
        """start the uninstall transaction"""
        engine = self.engine_kls(self.old_pkg, offset=self.offset,
            observer=self.observer)
        self.old_pkg.add_format_triggers(self, self.uninstall_op, engine)
        self._add_triggers(engine)
        self.customize_engine(engine)
        return livefs_base.start(self, engine)

    def prerm(self):
        """execute any pre-removal steps required"""
        return self.uninstall_op.prerm()

    def remove(self):
        """execute any removal steps required"""
        for unmerge_phase in (self.me.pre_unmerge, self.me.unmerge,
            self.me.post_unmerge):
            try:
                unmerge_phase()
            except merge_errors.NonFatalModification, e:
                print "warning caught: %s" % e
        return True

    def postrm(self):
        """execute any post-removal steps required"""
        return self.uninstall_op.postrm()

    def _notify_repo(self):
        self.repo.notify_remove_package(self.old_pkg)

    def unmerge_metadata(self):
        """unmerge pkg metadata from the repository.  Must be overrided."""
        raise NotImplementedError

    def finish(self):
        ret = self.uninstall_op.finalize()
        self.uninstall_op.cleanup(disable_observer=True)
        if not ret:
            logger.warn("ignoring unexpected result from uninstall finalize- "
                "%r" % ret)
        return livefs_base.finish(self)

    def __del__(self):
        if getattr(self, 'underway', False):
            print "warning: %s unmerge was underway, but wasn't completed" % \
                self.old_pkg
            self.lock.release_write_lock()


class livefs_replace(livefs_install, livefs_uninstall):

    """base interface for replacing a pkg in a livefs repo with another.

    Repositories should override as needed.
    """

    stage_depends = {
        "finish":"unmerge_metadata",
        "unmerge_metadata":"postinst",
        "postinst":"postrm",
        "postrm":"remove",
        "remove":"prerm",
        "prerm":"merge_metadata",
        "merge_metadata":"transfer",
        "transfer":"preinst",
        "preinst":"start"}

    stage_hooks = [
        "merge_metadata", "unmerge_metadata", "postrm", "prerm", "postinst",
        "preinst", "unmerge_metadata", "merge_metadata"]
    engine_kls = staticmethod(MergeEngine.replace)

    def __init__(self, repo, oldpkg, newpkg, observer, triggers, offset):
        self.old_pkg = oldpkg
        self.new_pkg = newpkg
        livefs_base.__init__(self, repo, observer, triggers, offset)

    def get_op(self):
        livefs_install.get_op(self)
        livefs_uninstall.get_op(self)

    def start(self):
        """start the transaction"""
        engine = self.engine_kls(self.old_pkg, self.new_pkg,
            offset=self.offset, observer=self.observer)
        self.old_pkg.add_format_triggers(self, self.uninstall_op, engine)
        self.new_pkg.add_format_triggers(self, self.install_op, engine)
        self._add_triggers(engine)
        self.customize_engine(engine)
        return livefs_base.start(self, engine)

    def _notify_repo(self):
        self.repo.notify_remove_package(self.old_pkg)
        self.repo.notify_add_package(self.new_pkg)

    def finish(self):
        ret = self.install_op.finalize()
        if not ret:
            logger.warn("ignoring unexpected result from install finalize- "
                "%r" % ret)
        ret = self.uninstall_op.finalize()
        self.uninstall_op.cleanup(disable_observer=True)
        if not ret:
            logger.warn("ignoring unexpected result from uninstall finalize- "
                "%r" % ret)
        return livefs_base.finish(self)

    def __del__(self):
        if getattr(self, 'underway', False):
            print "warning: %s -> %s replacement was underway, " \
                "but wasn't completed" % (self.old_pkg, self.new_pkg)
            self.lock.release_write_lock()


class operations(object):

    def __init__(self, repository, disable_overrides=(), enable_overrides=()):
        self.repo = repository
        enabled_ops = set(self._filter_disabled_commands(
            self._collect_operations()))
        enabled_ops.update(enable_overrides)
        enabled_ops.difference_update(disable_overrides)

        for op in enabled_ops:
            self._enable_operation(op)

        self._enabled_ops = frozenset(enabled_ops)

    def _filter_disabled_commands(self, sequence):
        for command in sequence:
            check_f = getattr(self, '_cmd_check_support_%s' % command, None)
            if check_f is not None and not check_f():
                continue
            yield command

    def _enable_operation(self, operation):
        setattr(self, operation,
            getattr(self, '_cmd_enabled_%s' % operation))

    def _disabled_if_frozen(self, command):
        if self.repo.frozen:
            logger.debug("disabling repo(%r) command(%r) due to repo being frozen",
                self.repo, command)
        return not self.repo.frozen

    @classmethod
    def _collect_operations(cls):
        for x in dir(cls):
            if x.startswith("_cmd_") and not x.startswith("_cmd_enabled_") \
                and not x.startswith("_cmd_check_support_"):
                yield x[len("_cmd_"):]

    def supports(self, operation_name=None, raw=False):
        if not operation_name:
            if not raw:
                return self._enabled_ops
            return frozenset(self._collect_operations())
        if raw:
            return hasattr(self, '_cmd_enabled_%s' % operation_name)
        return hasattr(self, operation_name)

    #def __dir__(self):
    #    return list(self._enabled_ops)

    def _default_observer(self, observer):
        if observer is None:
            observer = observer_mod.repo_observer()
        return observer

    def _cmd_enabled_install(self, pkg, observer=None):
        return self._cmd_install(pkg,
            self._default_observer(observer))

    def _cmd_enabled_uninstall(self, pkg, observer=None):
        return self._cmd_uninstall(pkg,
            self._default_observer(observer))

    def _cmd_enabled_replace(self, oldpkg, newpkg, observer=None):
        return self._cmd_replace(oldpkg, newpkg,
            self._default_observer(observer))

    for x in ("install", "uninstall", "replace"):
        locals()["_cmd_check_support_%s" % x] = post_curry(
            _disabled_if_frozen, x)

    del x

    def _cmd_enabled_configure(self, pkg, observer=None):
        return self._cmd_configure(self.repository, pkg,
            self._default_observer(observer))

    def _cmd_enabled_sync(self, observer=None):
        # often enough, the syncer is a lazy_ref
        return self._cmd_sync(self._default_observer(observer))

    def _cmd_sync(self, observer):
        return self._get_syncer().sync()
        return syncer.sync()

    def _get_syncer(self):
        syncer = self.repo._syncer
        if not isinstance(syncer, sync.base.syncer):
            syncer = syncer.instantiate()
        return syncer

    def _cmd_check_support_sync(self):
        return getattr(self.repo, '_syncer', None) is not None \
            and not self._get_syncer().disabled


class operations_proxy(operations):

    def __init__(self, repository, *args, **kwds):
        self.repo = repository
        for attr in self._get_target_attrs():
            if attr.startswith("_cmd_"):
                if attr.startswith("_cmd_check_support_"):
                    setattr(self, attr, partial(self._proxy_op_support, attr))
                elif not attr.startswith("_cmd_enabled_"):
                    setattr(self, attr, partial(self._proxy_op, attr))
        operations.__init__(self, repository, *args, **kwds)

    def _get_target_attrs(self):
        return dir(self.repo.raw_repo.operations)

    def _proxy_op(self, op_name, *args, **kwds):
        return getattr(self.repo.raw_repo.operations, op_name)(*args, **kwds)

    _proxy_op_support = _proxy_op

    def _collect_operations(self):
        return self.repo.raw_repo.operations._collect_operations()
