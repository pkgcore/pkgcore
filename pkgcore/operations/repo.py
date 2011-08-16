# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
repository modifications (installing, removing, replacing)
"""

__all__ = ("Failure", "base", "install", "uninstall", "replace",
    "operations", "operations_proxy")

from snakeoil.dependant_methods import ForcedDepends
from snakeoil.weakrefs import WeakRefFinalizer
from snakeoil.currying import partial, post_curry
from pkgcore.operations import base as operations_base
from snakeoil.demandload import demandload
demandload(globals(), "pkgcore.log:logger",
    "pkgcore.operations:observer@observer_mod",
    "pkgcore:sync",
    "pkgcore.package.mutated:MutatedPkg",
    )


class fake_lock(object):
    def __init__(self):
        pass

    acquire_write_lock = acquire_read_lock = __init__
    release_read_lock = release_write_lock = __init__


class finalizer_base(WeakRefFinalizer, ForcedDepends):

    pass

class Failure(Exception):
    pass


class base(object):

    __metaclass__ = ForcedDepends

    stage_depends = {}

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

    def finalize_data(self):
        raise NotImplementedError(self, 'finalize_data')

    def finish(self):
        self.lock.release_write_lock()
        self.underway = False
        return True


class install(base):

    stage_depends = {'finish': '_notify_repo_add',
        '_notify_repo_add': 'finalize_data',
        'finalize_data': 'add_data',
        'add_data':'start'}

    description = "install"

    def __init__(self, repo, pkg, observer):
        base.__init__(self, repo, observer)
        self.new_pkg = pkg

    def _notify_repo_add(self):
        self.repo.notify_add_package(self.new_pkg)
        return True

    def add_data(self):
        raise NotImplementedError(self, 'add_data')

    def _update_pkg_contents(self, contents):
        self.new_pkg = MutatedPkg(self.new_pkg,
            {"contents":contents})


class uninstall(base):

    stage_depends = {'finish': '_notify_repo_remove',
        '_notify_repo_remove': 'finalize_data',
        'finalize_data': 'remove_data',
        'remove_data':'start'}

    description = "uninstall"

    def __init__(self, repo, pkg, observer):
        base.__init__(self, repo, observer)
        self.old_pkg = pkg

    def _notify_repo_remove(self):
        self.repo.notify_remove_package(self.old_pkg)
        return True

    def remove_data(self):
        raise NotImplementedError(self, 'remove_data')


class replace(install, uninstall):

    stage_depends = {'finish': '_notify_repo_add',
        '_notify_repo_add': 'finalize_data',
        'finalize_data': ('add_data', '_notify_repo_remove'),
        '_notify_repo_remove': 'remove_data',
        'remove_data': 'start',
        'add_data': 'start'}

    description = "replace"

    def __init__(self, repo, oldpkg, newpkg, observer):
        # yes there is duplicate initialization here.
        uninstall.__init__(self, repo, oldpkg, observer)
        install.__init__(self, repo, newpkg, observer)


class operations(operations_base):

    def __init__(self, repository, disable_overrides=(), enable_overrides=()):
        self.repo = repository
        operations_base.__init__(self, disable_overrides, enable_overrides)

    def _disabled_if_frozen(self, command):
        if self.repo.frozen:
            logger.debug("disabling repo(%r) command(%r) due to repo being frozen",
                self.repo, command)
        return not self.repo.frozen

    def _default_observer(self, observer):
        if observer is None:
            observer = observer_mod.repo_observer()
        return observer

    def _cmd_api_install(self, pkg, observer=None):
        return self._cmd_implementation_install(pkg,
            self._default_observer(observer))

    def _cmd_api_uninstall(self, pkg, observer=None):
        return self._cmd_implementation_uninstall(pkg,
            self._default_observer(observer))

    def _cmd_api_replace(self, oldpkg, newpkg, observer=None):
        return self._cmd_implementation_replace(oldpkg, newpkg,
            self._default_observer(observer))

    def _cmd_api_install_or_replace(self, newpkg, observer=None):
        return self._cmd_implementation_install_or_replace(newpkg,
            self._default_observer(observer))

    def _cmd_implementation_install_or_replace(self, newpkg, observer=None):
        match = self.repo.match(newpkg.versioned_atom)
        if not match:
            return self.install(newpkg, observer=observer)
        assert len(match) == 1
        return self.replace(match[0], newpkg, observer=observer)

    for x in ("install", "uninstall", "replace", "install_or_replace"):
        locals()["_cmd_check_support_%s" % x] = post_curry(
            _disabled_if_frozen, x)

    del x

    def _cmd_api_configure(self, pkg, observer=None):
        return self._cmd_implementation_configure(self.repository, pkg,
            self._default_observer(observer))

    def _cmd_api_sync(self, observer=None):
        # often enough, the syncer is a lazy_ref
        return self._cmd_implementation_sync(self._default_observer(observer))

    def _cmd_implementation_sync(self, observer):
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
                elif not attr.startswith("_cmd_api_"):
                    setattr(self, attr, partial(self._proxy_op, attr))
        operations.__init__(self, repository, *args, **kwds)

    def _get_target_attrs(self):
        return dir(self.repo.raw_repo.operations)

    def _proxy_op(self, op_name, *args, **kwds):
        return getattr(self.repo.raw_repo.operations, op_name)(*args, **kwds)

    _proxy_op_support = _proxy_op

    def _collect_operations(self):
        return self.repo.raw_repo.operations._collect_operations()
