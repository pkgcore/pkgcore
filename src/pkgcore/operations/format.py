"""
build operation
"""

__all__ = (
    'build_base', 'install', 'uninstall', 'replace', 'fetch_base',
    'empty_build_op', 'FailedDirectory', 'GenericBuildError',
)

import os

from snakeoil import klass
from snakeoil.dependant_methods import ForcedDepends
from snakeoil.osutils import pjoin
from snakeoil.sequences import iflatten_instance

from .. import fetch as _fetch_module
from .. import operations as _operations_mod
from ..exceptions import PkgcoreUserException
from ..fetch import errors as fetch_errors


class fetch_base:

    def __init__(self, domain, pkg, fetchables, fetcher):
        self.verified_files = {}
        self._basenames = set()
        self.domain = domain
        self.pkg = pkg
        self.fetchables = fetchables
        self.fetcher = fetcher

    def fetch_all(self, observer):
        # TODO: add parallel fetch support
        failures = []
        for fetchable in self.fetchables:
            if not self.fetch_one(fetchable, observer):
                failures.append(fetchable)
        if failures:
            self._failed_fetch(failures, observer)
            return False
        return True

    def fetch_one(self, fetchable, observer, retry=False):
        if fetchable.filename in self._basenames:
            return True
        # fetching files without uri won't fly
        # XXX hack atm, could use better logic but works for now
        try:
            fp = self.fetcher(fetchable)
        except fetch_errors.ChksumFailure as e:
            # checksum failed, rename file and try refetching
            path = pjoin(self.fetcher.distdir, fetchable.filename)
            failed_filename = f'{fetchable.filename}._failed_chksum_'
            failed_path = pjoin(self.fetcher.distdir, failed_filename)
            os.rename(path, failed_path)
            if retry:
                raise
            observer.error(str(e))
            observer.error(f'renaming to {failed_filename!r} and refetching from upstream')
            observer.flush()
            # refetch directly from upstream
            return self.fetch_one(fetchable.upstream, observer, retry=True)
        except fetch_errors.FetchFailed as e:
            fp = None
        if fp is None:
            return False
        self.verified_files[fp] = fetchable
        self._basenames.add(fetchable.filename)
        return True

    def _failed_fetch(self, fetchables, observer):
        # run pkg_nofetch phase for fetch restricted pkgs
        if 'fetch' in self.pkg.restrict:
            # This requires wrapped packages from a configured repo, otherwise
            # buildables aren't available to run the pkg_nofetch phase.
            configured_repo = self.domain.unfiltered_repos[self.pkg.repo.repo_id]
            pkgwrap = configured_repo.package_class(self.pkg)
            build_ops = self.domain.build_pkg(pkgwrap, observer, failed=True)
            build_ops.nofetch()
            build_ops.cleanup(force=True)
        observer.error("failed fetching files: %s::%s", self.pkg.cpvstr, self.pkg.repo.repo_id)


class operations(_operations_mod.base):

    _fetch_kls = fetch_base

    def __init__(self, domain, pkg, observer=None, disable_overrides=(),
                 enable_overrides=()):
        self.observer = observer
        self.pkg = pkg
        self.domain = domain
        super().__init__(disable_overrides, enable_overrides)

    def _cmd_api_info(self):
        return self._cmd_implementation_info()

    @_operations_mod.is_standalone
    def _cmd_api_mergable(self):
        return getattr(self.pkg, 'built', False)

    def _cmd_api_sanity_check(self):
        return self._cmd_implementation_sanity_check(self.domain)

    def _cmd_implementation_sanity_check(self, domain):
        return True

    def _cmd_api_localize(self, force=False, observer=klass.sentinel):
        observer = observer if observer is not klass.sentinel else self.observer
        return self._cmd_implementation_localize(
            self._get_observer(observer), force=force)

    def _cmd_api_cleanup(self, force=False, observer=klass.sentinel):
        observer = observer if observer is not klass.sentinel else self.observer
        return self._cmd_implementation_cleanup(
            self._get_observer(observer), force=force)

    def _cmd_api_configure(self, observer=klass.sentinel):
        observer = observer if observer is not klass.sentinel else self.observer
        return self._cmd_implementation_configure(
            self._get_observer(observer))

    def _cmd_check_support_fetch(self):
        return self._find_fetcher() is not None

    def _generate_fetchables(self, mirroring=False):
        pkg = self.pkg
        if not mirroring:
            return pkg.fetchables
        pkg = getattr(pkg, '_raw_pkg', pkg)
        return tuple(iflatten_instance(pkg.fetchables, _fetch_module.fetchable))

    @klass.cached_property
    def _fetch_op(self):
        return self._fetch_kls(
            self.domain, self.pkg,
            self._generate_fetchables(),
            self._find_fetcher())

    @klass.cached_property
    def _mirror_op(self):
        return self._fetch_kls(
            self.domain, self.pkg,
            self._generate_fetchables(mirroring=True),
            self._find_fetcher())

    @_operations_mod.is_standalone
    def _cmd_api_fetch(self, fetchables=None, observer=klass.sentinel):
        observer = observer if observer is not klass.sentinel else self.observer
        if fetchables is None:
            fetcher = self._fetch_op
        else:
            if not isinstance(fetchables, (tuple, list)):
                fetchables = [fetchables]
            fetcher = self._fetch_kls(self.domain, self.pkg, fetchables, self._find_fetcher())
        return fetcher.fetch_all(self._get_observer(observer))

    @_operations_mod.is_standalone
    def _cmd_api_mirror(self, observer=klass.sentinel):
        observer = observer if observer is not klass.sentinel else self.observer
        return self._mirror_op.fetch_all(self._get_observer(observer))

    def _find_fetcher(self):
        fetcher = getattr(self.pkg.repo, 'fetcher', None)
        if fetcher is None:
            return getattr(self.domain, 'fetcher', None)
        return fetcher


class build_operations(operations):

    __required__ = frozenset(["build"])

    def _cmd_api_build(self, observer=None, failed=False, clean=True, **kwargs):
        if failed:
            verified_files = None
        else:
            verified_files = self._fetch_op.verified_files
        return self._cmd_implementation_build(
            self._get_observer(observer),
            verified_files,
            clean=clean, **kwargs)

    def _cmd_api_buildable(self, domain):
        return self._cmd_implementation_buildable(domain)

    def _cmd_implementation_buildable(self, domain):
        return True


class build_base(metaclass=ForcedDepends):

    stage_depends = {'finish': 'start'}

    def __init__(self, domain, observer):
        self.domain = domain
        self.observer = observer

    def start(self):
        return True

    def finish(self):
        return True


class build(build_base):

    stage_depends = {
        "setup": "start",
        "unpack": "setup",
        "configure": "prepare",
        "prepare": "unpack",
        "compile": "configure",
        "test": "compile",
        "install": "test",
        "finalize": "install",
    }

    def __init__(self, domain, pkg, verified_files, observer):
        super().__init__(domain, observer)
        self.pkg = pkg
        self.verified_files = verified_files

    def setup(self):
        return True

    def unpack(self):
        return True

    def prepare(self):
        return True

    def configure(self):
        return True

    def compile(self):
        return True

    def test(self):
        return True

    def install(self):
        return True

    def finalize(self):
        """finalize any build steps required"""
        return True

    def cleanup(self):
        """cleanup any working files/dirs created during building"""
        return True

    for k in ("setup", "unpack", "configure", "compile", "test", "install"):
        locals()[k].__doc__ = (
            "execute any %s steps required; "
            "implementations of this interface should overide this as needed"
            % k)
    for k in ("setup", "unpack", "configure", "compile", "test", "install", "finalize"):
        o = locals()[k]
        o.__doc__ = "\n".join(x.lstrip() for x in o.__doc__.split("\n") + [
                              ":return: True on success, False on failure"])
    del o, k


class install(build_base):

    stage_depends = {
        "preinst": "start",
        "postinst": "preinst",
        "finalize": "postinst",
    }

    def __init__(self, domain, newpkg, observer):
        super().__init__(domain, observer)
        self.new_pkg = self.pkg = newpkg

    def add_triggers(self, engine):
        pass

    def preinst(self):
        """any pre merge steps needed"""
        return True

    def postinst(self):
        """any post merge steps needed"""
        return True

    def finalize(self):
        """finalize any merge steps required"""
        return True


class uninstall(build_base):

    stage_depends = {
        "prerm": "start",
        "postrm": "prerm",
        "finalize": "postrm",
    }

    def __init__(self, domain, oldpkg, observer):
        super().__init__(domain, observer)
        self.old_pkg = self.pkg = oldpkg

    def add_triggers(self, engine):
        pass

    def prerm(self):
        """any pre unmerge steps needed"""
        return True

    def postrm(self):
        """any post unmerge steps needed"""
        return True

    def postinst(self):
        """any post unmerge steps needed"""
        return True

    def finalize(self):
        """finalize any unmerge steps required"""
        return True


class replace(install, uninstall):

    stage_depends = {
        "finalize": "postinst",
        "postinst": "postrm",
        "postrm": "prerm",
        "prerm": "preinst",
        "preinst": "start",
    }

    def __init__(self, domain, old_pkg, new_pkg, observer):
        build_base.__init__(self, domain, observer)
        self.new_pkg = new_pkg
        self.old_pkg = old_pkg


class empty_build_op(build_base):

    stage_depends = {}

    def __init__(self, pkg, observer=None, clean=False):
        super().__init__(observer)
        self.pkg = pkg

    def cleanup(self):
        return True

    def finalize(self):
        return self.pkg


class BuildError(PkgcoreUserException):
    pass


class FailedDirectory(BuildError):
    def __init__(self, path, text):
        super().__init__(f"failed creating/ensuring dir {path}: {text}")


class GenericBuildError(BuildError):
    def __init__(self, err):
        super().__init__(f"failed build operation: {err}")
        self.err = str(err)
