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
from snakeoil import klass
from pkgcore import operations as _operations_mod
from snakeoil.demandload import demandload
demandload(globals(), "pkgcore.log:logger",
    "pkgcore.operations:observer@observer_mod,regen",
    "pkgcore.sync:base@_sync_base",
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

    def start(self, *args):
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


class sync_operations(_operations_mod.base):

    def __init__(self, repository, disable_overrides=(), enable_overrides=()):
        self.repo = repository
        _operations_mod.base.__init__(self, disable_overrides, enable_overrides)

    @_operations_mod.is_standalone
    def _cmd_api_sync(self, observer=None):
        # often enough, the syncer is a lazy_ref
        syncer = self._get_syncer()
        return syncer.sync()

    def _get_syncer(self, lazy=False):
        singleton = object()
        syncer = getattr(self.repo, '_syncer', singleton)
        if syncer is singleton:
            # raw repo's vs non-raw; drive down to the raw repo.
            # see pkgcore.ebuild.repository for an example
            syncer = getattr(self.repo, 'config', None)
            syncer = getattr(syncer, '_syncer', None)

        if not lazy and not isinstance(syncer, _sync_base.syncer):
            syncer = syncer.instantiate()
        return syncer

    def _cmd_check_support_sync(self):
        syncer = self._get_syncer(lazy=True)
        if syncer is not None:
            return not self._get_syncer().disabled
        return False


class operations(sync_operations):

    def _disabled_if_frozen(self, command):
        if self.repo.frozen:
            logger.debug("disabling repo(%r) command(%r) due to repo being frozen",
                self.repo, command)
        return not self.repo.frozen

    def _get_observer(self, observer=None):
        if observer is None:
            observer = observer_mod.repo_observer(observer_mod.null_output())
        return observer

    def _cmd_api_install(self, pkg, observer=None):
        return self._cmd_implementation_install(pkg,
            self._get_observer(observer))

    def _cmd_api_uninstall(self, pkg, observer=None):
        return self._cmd_implementation_uninstall(pkg,
            self._get_observer(observer))

    def _cmd_api_replace(self, oldpkg, newpkg, observer=None):
        return self._cmd_implementation_replace(oldpkg, newpkg,
            self._get_observer(observer))

    def _cmd_api_install_or_replace(self, newpkg, observer=None):
        return self._cmd_implementation_install_or_replace(newpkg,
            self._get_observer(observer))

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
            self._get_observer(observer))

    @_operations_mod.is_standalone
    def _cmd_api_regen_cache(self, observer=None, threads=1, **options):
        if getattr(self, '_regen_disable_threads', False):
            threads = 1
        cache = getattr(self.repo, 'cache', None)
        sync_rate = getattr(cache, 'sync_rate', None)
        try:
            if sync_rate is not None:
                cache.set_sync_rate(1000000)
            return regen.regen_repository(self.repo,
                self._get_observer(observer), threads=threads, **options)
        finally:
            if sync_rate is not None:
                cache.set_sync_rate(sync_rate)
            self.repo.operations.run_if_supported("flush_cache")

    def _get_caches(self):
        caches = getattr(self.repo, 'cache', ())
        if not hasattr(caches, 'commit'):
            return caches
        return [caches]

    @_operations_mod.is_standalone
    def _cmd_api_flush_cache(self, observer=None):
        for cache in self._get_caches():
            cache.commit(force=True)

    def _cmd_api_digests(self, domain, query, observer=None, **options):
        observer = self._get_observer(observer)
        matches = self.repo.match(query)
        if not matches:
            observer.debug("skipping digest of query %s; no matches\n" % (query,))
            return True
        return self._cmd_implementation_digests(domain, matches,
            observer, **options)


class operations_proxy(operations):

    # cache this; this is to prevent the target operations mutating resulting in
    # our proxy setup not matching the target.
    @klass.cached_property
    def raw_operations(self):
        return self.repo.raw_repo.operations

    @klass.cached_property
    def enabled_operations(self):
        s = set(self.raw_operations.enabled_operations)
        return frozenset(self._apply_overrides(s))

    def _setup_api(self):
        for op in self.raw_operations.enabled_operations:
            setattr(self, op, partial(self._proxy_op, op))

    def _proxy_op(self, op_name, *args, **kwds):
        return getattr(self.raw_operations, op_name)(*args, **kwds)
