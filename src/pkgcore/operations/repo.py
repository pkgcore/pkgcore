"""
repository modifications (installing, removing, replacing)
"""

__all__ = (
    "Failure", "base", "install", "uninstall", "replace",
    "operations", "operations_proxy"
)

from functools import partial

from snakeoil import klass
from snakeoil.currying import post_curry
from snakeoil.dependant_methods import ForcedDepends

from .. import operations as operations_mod
from ..exceptions import PkgcoreException
from ..log import logger
from ..package.mutated import MutatedPkg
from ..restrictions import packages
from ..sync import base as _sync_base
from . import observer as observer_mod
from . import regen


class fake_lock:
    def __init__(self):
        pass

    acquire_write_lock = acquire_read_lock = __init__
    release_read_lock = release_write_lock = __init__


class Failure(PkgcoreException):
    pass


class base(metaclass=ForcedDepends):

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

    stage_depends = {
        'finish': '_notify_repo_add',
        '_notify_repo_add': 'finalize_data',
        'finalize_data': 'add_data',
        'add_data': 'start'
    }

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
        self.new_pkg = MutatedPkg(self.new_pkg, {"contents": contents})


class uninstall(base):

    stage_depends = {
        'finish': '_notify_repo_remove',
        '_notify_repo_remove': 'finalize_data',
        'finalize_data': 'remove_data',
        'remove_data': 'start'
    }

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

    stage_depends = {
        'finish': '_notify_repo_add',
        '_notify_repo_add': 'finalize_data',
        'finalize_data': ('add_data', '_notify_repo_remove'),
        '_notify_repo_remove': 'remove_data',
        'remove_data': 'start',
        'add_data': 'start'
    }

    description = "replace"

    def __init__(self, repo, oldpkg, newpkg, observer):
        # yes there is duplicate initialization here.
        uninstall.__init__(self, repo, oldpkg, observer)
        install.__init__(self, repo, newpkg, observer)


class sync_operations(operations_mod.base):

    def __init__(self, repository, disable_overrides=(), enable_overrides=()):
        self.repo = repository
        super().__init__(disable_overrides, enable_overrides)

    @operations_mod.is_standalone
    def _cmd_api_sync(self, observer=None, **kwargs):
        # often enough, the syncer is a lazy_ref
        syncer = self._get_syncer()
        self.repo._pre_sync()
        ret = syncer.sync(**kwargs)
        self.repo._post_sync()
        return ret

    def _get_syncer(self, lazy=False):
        syncer = getattr(self.repo, '_syncer', klass.sentinel)
        if syncer is klass.sentinel:
            # raw repo's vs non-raw; drive down to the raw repo.
            # see pkgcore.ebuild.repository for an example
            syncer = getattr(self.repo, 'config', None)
            syncer = getattr(syncer, '_syncer', None)

        if not lazy and not isinstance(syncer, _sync_base.Syncer):
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
            logger.debug(
                "disabling repo(%r) command(%r) due to repo being frozen",
                self.repo, command)
        return not self.repo.frozen

    def _get_observer(self, observer=None):
        if observer is None:
            observer = observer_mod.repo_observer(observer_mod.null_output())
        return observer

    def _cmd_api_install(self, pkg, observer=None):
        return self._cmd_implementation_install(
            pkg, self._get_observer(observer))

    def _cmd_api_uninstall(self, pkg, observer=None):
        return self._cmd_implementation_uninstall(
            pkg, self._get_observer(observer))

    def _cmd_api_replace(self, oldpkg, newpkg, observer=None):
        return self._cmd_implementation_replace(
            oldpkg, newpkg, self._get_observer(observer))

    def _cmd_api_install_or_replace(self, newpkg, observer=None):
        return self._cmd_implementation_install_or_replace(
            newpkg, self._get_observer(observer))

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
        return self._cmd_implementation_configure(
            self.repo, pkg, self._get_observer(observer))

    def _cmd_implementation_clean_cache(self, pkgs=None):
        """Clean stale and invalid cache entries up."""
        caches = [x for x in self._get_caches() if not x.readonly]
        if not caches:
            return
        if pkgs is None:
            pkgs = frozenset(pkg.cpvstr for pkg in self.repo)
        for cache in caches:
            cache_pkgs = frozenset(cache)
            for p in cache_pkgs - pkgs:
                del cache[p]

    @operations_mod.is_standalone
    def _cmd_api_regen_cache(self, observer=None, threads=1, **kwargs):
        cache = getattr(self.repo, 'cache', None)
        if not cache and not kwargs.get('force', False):
            return
        sync_rate = getattr(cache, 'sync_rate', None)
        try:
            if sync_rate is not None:
                cache.set_sync_rate(1000000)
            errors = 0

            # Force usage of unfiltered repo to include pkgs with metadata issues.
            # Matches are collapsed directly to a list to avoid threading issues such
            # as EBADF since the repo iterator isn't thread-safe.
            pkgs = list(self.repo.itermatch(packages.AlwaysTrue, pkg_filter=None))

            observer = self._get_observer(observer)
            for pkg, e in regen.regen_repository(
                    self.repo, pkgs, observer=observer, threads=threads, **kwargs):
                observer.error(f'caught exception {e} while processing {pkg.cpvstr}')
                errors += 1

            # report pkgs with bad metadata -- relies on iterating over the
            # unfiltered repo to populate the masked repo
            pkgs = frozenset(pkg.cpvstr for pkg in self.repo)
            for pkg in sorted(self.repo._bad_masked):
                observer.error(f'{pkg.cpvstr}: {pkg.data.msg(verbosity=observer.verbosity)}')
                errors += 1

            # remove old/invalid cache entries
            self._cmd_implementation_clean_cache(pkgs)

            return errors
        finally:
            if sync_rate is not None:
                cache.set_sync_rate(sync_rate)
            self.repo.operations.run_if_supported("flush_cache")

    def _get_caches(self):
        caches = getattr(self.repo, 'cache', ())
        if not hasattr(caches, 'commit'):
            return caches
        return [caches]

    @operations_mod.is_standalone
    def _cmd_api_flush_cache(self, observer=None):
        for cache in self._get_caches():
            cache.commit(force=True)

    def _cmd_api_digests(self, domain, restriction, observer=None,
                         mirrors=False, force=False):
        observer = self._get_observer(observer)
        matches = self.repo.match(restriction)
        if not matches:
            return matches
        return self._cmd_implementation_digests(
            domain, matches, observer, mirrors, force)


class operations_proxy(operations):

    # cache this; this is to prevent the target operations mutating resulting
    # in our proxy setup not matching the target.
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

    def _proxy_op(self, op_name, *args, **kwargs):
        return getattr(self.raw_operations, op_name)(*args, **kwargs)
