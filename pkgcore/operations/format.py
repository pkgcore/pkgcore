# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
build operation
"""

__all__ = ('build_base', 'install', 'uninstall', 'replace', 'fetch',
    'empty_build_op', 'FailedDirectory', 'GenericBuildError', 'errors')

from pkgcore import operations as _operations_mod
from snakeoil.dependant_methods import ForcedDepends

def _raw_fetch(self):
    if not "files" in self.__dict__:
        self.files = {}

    # this is being anal, but protect against pkgs that don't collapse
    # common uri down to a single file.
    gotten_fetchables = set(x.filename for x in self.files.values())
    for x in self.fetchables:
        if x.filename in gotten_fetchables:
            continue
        # fetching files without uri won't fly
        # XXX hack atm, could use better logic but works for now
        fp = self.fetcher(x)
        if fp is None:
            if x.uri:
                return False
            self.nofetch()
            return False
        self.files[fp] = x
        gotten_fetchables.add(x.filename)
    return True


class operations(_operations_mod.base):

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


class build_operations(operations):

    __required__ = frozenset(["build"])

    def _cmd_api_build(self, observer=None, clean=True):
        return self._cmd_implementation_build(observer=observer, clean=clean)

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
        "unpack":("fetch", "setup"),
        "configure":"prepare",
        "prepare":"unpack",
        "compile":"configure",
        "test":"compile",
        "install":"test",
        "finalize":"install"}

    def __init__(self, domain, pkg, observer):
        build_base.__init__(self, domain, observer)
        self.pkg = pkg

    def setup(self):
        return True

    fetch = _raw_fetch

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
        "setup", "fetch", "unpack", "configure", "compile", "test", "install"):
        locals()[k].__doc__ = (
            "execute any %s steps required; "
            "implementations of this interface should overide this as needed"
            % k)
    for k in (
        "setup", "fetch", "unpack", "configure", "compile", "test", "install",
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


class fetch(object):
    __metaclass__ = ForcedDepends

    stage_depends = {"finalize":"fetch"}

    fetch = _raw_fetch

    def __init__(self, pkg):
        self.pkg = pkg
        self.fetchables = pkg.fetchables

    def finalize(self):
        """finalize any build steps required"""
        return self.pkg

    def cleanup(self):
        return True


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
