# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
build operation
"""

__all__ = ('build_base', 'install', 'uninstall', 'replace', 'fetch_base',
    'empty_build_op', 'FailedDirectory', 'GenericBuildError', 'errors')

from pkgcore import operations as _operations_mod
from snakeoil.dependant_methods import ForcedDepends
from snakeoil import klass


class fetch_base(object):

    def __init__(self, domain, pkg, fetcher):
        self.verified_files = {}
        self._basenames = set()
        self.domain = domain
        self.pkg = pkg
        self.fetcher = fetcher

    def fetch_all(self, observer):
        for fetchable in self.pkg.fetchables:
            if not self.fetch_one(fetchable, observer):
                return False
        return True

    def fetch_one(self, fetchable, observer):
        if fetchable.filename in self._basenames:
            return True
        # fetching files without uri won't fly
        # XXX hack atm, could use better logic but works for now
        fp = self.fetcher(fetchable)
        if fp is None:
            self.failed_fetch(fetchable, observer)
            return False
        self.verified_files[fp] = fetchable
        self._basenames.add(fetchable.filename)
        return True

    def failed_fetch(self, fetchable, observer):
        observer.error("failed fetching %s" % (fetchable,))


class operations(_operations_mod.base):

    _fetch_kls = fetch_base

    def __init__(self, domain, pkg, observer=None, disable_overrides=(),
        enable_overrides=()):
        self.observer = observer
        self.pkg = pkg
        self.domain = domain
        _operations_mod.base.__init__(self, disable_overrides, enable_overrides)

    def _cmd_api_info(self):
        return self._cmd_implementation_info()

    @_operations_mod.is_standalone
    def _cmd_api_mergable(self):
        return getattr(self.pkg, 'built', False)

    def _cmd_api_sanity_check(self):
        return self._cmd_implementation_sanity_check(self.domain)

    def _cmd_implementation_sanity_check(self, domain):
        return True

    def _cmd_api_localize(self, observer=None, force=False):
        return self._cmd_implementation_localize(
            self._get_observer(observer), force=force)

    def _cmd_api_cleanup(self, observer=None, force=False):
        return self._cmd_implementation_cleanup(
            self._get_observer(observer), force=force)

    def _cmd_api_configure(self, observer=None):
        return self._cmd_implementation_configure(
            self._get_observer(observer))

    def _cmd_check_support_fetch(self):
        return self._find_fetcher() is not None

    @klass.cached_property
    def _fetch_op(self):
        return self._fetch_kls(self.domain, self.pkg, self._find_fetcher())

    @_operations_mod.is_standalone
    def _cmd_api_fetch(self, observer=None):
        return self._fetch_op.fetch_all(
            self._get_observer(observer))

    def _find_fetcher(self):
        fetcher = getattr(self.pkg.repo, 'fetcher', None)
        if fetcher is None:
            return getattr(self.domain, 'fetcher', None)
        return fetcher


class build_operations(operations):

    __required__ = frozenset(["build"])

    def _cmd_api_build(self, observer=None, clean=True):
        return self._cmd_implementation_build(self._get_observer(observer),
            self._fetch_op.verified_files,
            clean=clean)

    def _cmd_api_buildable(self, domain):
        return self._cmd_implementation_buildable(domain)

    def _cmd_implementation_buildable(self, domain):
        return True


class build_base(object):
    stage_depends = {'finish':'start'}

    __metaclass__ = ForcedDepends

    def __init__(self, domain, observer):
        self.domain = domain
        self.observer = observer

    def start(self):
        return True

    def finish(self):
        return True


class build(build_base):
    stage_depends = {
        "setup":"start",
        "unpack":"setup",
        "configure":"prepare",
        "prepare":"unpack",
        "compile":"configure",
        "test":"compile",
        "install":"test",
        "finalize":"install"}

    def __init__(self, domain, pkg, verified_files, observer):
        build_base.__init__(self, domain, observer)
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

    for k in (
        "setup", "unpack", "configure", "compile", "test", "install"):
        locals()[k].__doc__ = (
            "execute any %s steps required; "
            "implementations of this interface should overide this as needed"
            % k)
    for k in (
        "setup", "unpack", "configure", "compile", "test", "install",
        "finalize"):
        o = locals()[k]
        o.__doc__ = "\n".join(x.lstrip() for x in o.__doc__.split("\n") + [
                ":return: True on success, False on failure"])
    del o, k


class install(build_base):
    stage_depends = {"preinst":"start", "postinst":"preinst", "finalize":"postinst"}

    def __init__(self, domain, newpkg, observer):
        build_base.__init__(self, domain, observer)
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
    stage_depends = {"prerm":"start", "postrm":"prerm", "finalize":"postrm"}

    def __init__(self, domain, oldpkg, observer):
        build_base.__init__(self, domain, observer)
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

    stage_depends = {"finalize":"postinst", "postinst":"postrm",
        "postrm":"prerm", "prerm":"preinst", "preinst":"start"}

    def __init__(self, domain, old_pkg, new_pkg, observer):
        build_base.__init__(self, domain, observer)
        self.new_pkg = new_pkg
        self.old_pkg = old_pkg


class empty_build_op(build_base):

    stage_depends = {}

#	__metaclass__ = ForcedDepends

    def __init__(self, pkg, observer=None, clean=False):
        build_base.__init__(self, observer)
        self.pkg = pkg

    def cleanup(self):
        return True

    def finalize(self):
        return self.pkg


class BuildError(Exception):
    pass

class FailedDirectory(BuildError):
    def __init__(self, path, text):
        BuildError.__init__(
            self, "failed creating/ensuring dir %s: %s" % (path, text))


class GenericBuildError(BuildError):
    def __init__(self, err):
        BuildError.__init__(self, "Failed build operation: %s" % (err,))
        self.err = str(err)


errors = (FailedDirectory, GenericBuildError)
