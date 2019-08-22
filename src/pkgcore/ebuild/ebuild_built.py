"""
built ebuild packages (vdb packages and binpkgs are derivatives of this)
"""

__all__ = ("package", "package_factory")

from functools import partial
import re

from snakeoil import demandimport
from snakeoil.currying import post_curry
from snakeoil.data_source import local_source
from snakeoil.mappings import IndeterminantDict
from snakeoil.obj import DelayedInstantiation

from pkgcore import fetch
from pkgcore.ebuild import ebuild_src, conditionals, triggers
from pkgcore.ebuild.eapi import get_eapi
from pkgcore.fs.livefs import scan
from pkgcore.merge import engine
from pkgcore.package import metadata

# TODO: forcibly enable lazy imports to resolve circular module imports
with demandimport.enabled():
    from pkgcore.ebuild import ebd


def passthrough(inst, attr):
    return inst.data[attr]

def passthrough_repo(inst):
    repo = inst.data.get('source_repository')
    if repo is None:
        repo = inst.data.get('repository')
        # work around managers storing this in different places.
        if repo is None:
            # finally, do the strip ourselves since this can come
            # back as '\n' from binpkg Packages caches...
            repo = inst.data.get('REPO', '').strip()
            if not repo:
                repo = None
    if repo:
        return repo.strip()
    return None


def wrap_inst(self, wrap, inst):
    return wrap(inst(self), self.use)


def generate_eapi(self):
    eapi_magic = self.data.pop("EAPI", "0")
    if not eapi_magic:
        # "" means EAPI 0
        eapi_magic = '0'
    eapi = get_eapi(str(eapi_magic).strip())
    # This can return None... definitely the wrong thing right now
    # for an unsupported eapi. Fix it later.
    return eapi


def _chost_fallback(initial, self):
    o = self.data.get(initial)
    if o is None:
        o = self.data.get("CHOST")
        if o is None:
            return o
    return o.strip()


class package(ebuild_src.base):

    """
    built form of an ebuild
    """

    immutable = True
    allow_regen = False

    @property
    def tracked_attributes(self):
        return tuple(super().tracked_attributes) + ("contents", "use", "environment")

    @property
    def _operations(self):
        return ebd.built_operations

    # hack, not for consumer usage
    _is_from_source = False

    _empty_fetchable = conditionals.DepSet.parse('', fetch.fetchable, operators={})

    built = True

    _get_attr = dict(ebuild_src.package._get_attr)
    _get_attr.update((x, partial(_chost_fallback, x.upper()))
                     for x in ("cbuild", "chost", "ctarget"))
    _get_attr.update((x, post_curry(passthrough, x))
                     for x in ("contents", "environment"))
    _get_attr.update((x, lambda s,x=x: s.data.get(x.upper(), ""))
                     for x in ("cflags", "cxxflags", "ldflags"))
    _get_attr.update((x, lambda s,x=x: tuple(s.data.get(x.upper(), "").split()))
                     for x in ("distfiles", "iuse_effective", "inherited"))
    _get_attr["source_repository"] = passthrough_repo
    _get_attr["fetchables"] = lambda s: s._empty_fetchable
    _get_attr["use"] = lambda s: DelayedInstantiation(
        frozenset, lambda: frozenset(s.data["USE"].split()))
    _get_attr["eapi"] = generate_eapi

    __slots__ = tuple(set(_get_attr.keys()) - set(ebuild_src.package._get_attr.keys()))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._get_attr.update(
            (k, post_curry(
                wrap_inst,
                ebuild_src.package._config_wrappables[k],
                ebuild_src.package._get_attr[k]))
            for k in ebuild_src.package._config_wrappables
            if k in super(package, self).tracked_attributes)

    def _update_metadata(self, pkg):
        raise NotImplementedError()

    def _repo_install_op(self, domain, observer):
        return self._parent._generate_format_install_op(domain, self,
            observer)

    def _repo_uninstall_op(self, domain, observer):
        return self._parent._generate_format_uninstall_op(domain, self,
            observer)

    def _repo_replace_op(self, domain, old_pkg, observer):
        return self._parent._generate_format_replace_op(domain, old_pkg,
            self, observer)

    def _fetch_metadata(self):
        return self._parent._get_metadata(self)

    def __str__(self):
        return "built ebuild: %s" % (self.cpvstr)

    def build(self, **kwargs):
        return self.repo._generate_buildop(self)

    def add_format_triggers(self, *args, **kwds):
        return self._parent._add_format_triggers(self, *args, **kwds)

    @property
    def ebuild(self):
        o = self.data.get("ebuild")
        if o is not None:
            return o
        return self._parent._get_ebuild_src(self)

    @property
    def _mtime_(self):
        raise AttributeError(self, "_mtime_")


class fresh_built_package(package):

    __slots__ = ()
    _is_from_source = True


def generic_format_triggers(self, pkg, op_inst, format_op_inst, engine_inst):
    if (engine_inst.mode in (engine.REPLACE_MODE, engine.INSTALL_MODE)
            and pkg == engine_inst.new and pkg.repo is engine_inst.new.repo):
        if 'preinst' in pkg.mandatory_phases:
            t = triggers.preinst_contents_reset(format_op_inst)
            t.register(engine_inst)
        # for ebuild format, always check the syms.
        # this isn't perfect for binpkgs since if the binpkg is already
        # screwed, the target is in place already
        triggers.FixImageSymlinks(format_op_inst).register(engine_inst)

def _generic_format_install_op(self, domain, newpkg, observer):
    return ebd.install_op(domain, newpkg, observer)

def _generic_format_uninstall_op(self, domain, oldpkg, observer):
    return ebd.uninstall_op(domain, oldpkg, observer)

def _generic_format_replace_op(self, domain, oldpkg, newpkg, observer):
    return ebd.replace_op(domain, oldpkg, newpkg, observer)


class package_factory(metadata.factory):
    child_class = package

    # For the plugin system.
    priority = 5

    def _get_metadata(self, pkg):
        return self._parent_repo._get_metadata(pkg)

    def new_package(self, *args):
        inst = self._cached_instances.get(args)
        if inst is None:
            inst = self._cached_instances[args] = self.child_class(self, *args)
        return inst

    def _get_ebuild_path(self, pkg):
        return self._parent_repo._get_path(pkg)

    _generate_format_install_op = _generic_format_install_op
    _generate_format_uninstall_op = _generic_format_uninstall_op
    _generate_format_replace_op = _generic_format_replace_op
    _add_format_triggers = generic_format_triggers


class fake_package_factory(package_factory):
    """
    a fake package_factory, so that we can reuse the normal get_metadata hooks.

    a factory is generated per package instance, rather then one
    factory, N packages.

    Do not use this unless you know it's what your after; this is
    strictly for transitioning a built ebuild (still in the builddir)
    over to an actual repo. It literally is a mapping of original
    package data to the new generated instances data store.
    """

    def __init__(self, child_class):
        self.child_class = child_class
        self._parent_repo = None

    def new_package(self, pkg, image_root, environment_path):
        self.pkg = pkg
        self.image_root = image_root
        self.environment_path = environment_path
        # lambda redirects path to environment path
        obj = self.child_class(self, pkg.cpvstr)
        for x in self.pkg._raw_pkg.tracked_attributes:
            # bypass setattr restrictions.
            object.__setattr__(obj, x, getattr(self.pkg, x))
        object.__setattr__(obj, "use", self.pkg.use)
        object.__setattr__(obj, "_domain", self.pkg._domain)
        return obj

    def get_ebuild_src(self, pkg):
        return self.pkg.ebuild

    def scan_contents(self, location):
        return scan(location, offset=location, mutable=True)

    def _get_metadata(self, pkg):
        return IndeterminantDict(self.__pull_metadata)

    def __pull_metadata(self, key):
        if key == "contents":
            return self.scan_contents(self.image_root)
        elif key == "environment":
            return local_source(self.environment_path)
        else:
            try:
                return getattr(self.pkg, key)
            except AttributeError as e:
                raise KeyError(key) from e

    _generate_format_install_op = _generic_format_install_op
    _generate_format_uninstall_op = _generic_format_uninstall_op
    _generate_format_replace_op = _generic_format_replace_op
    _add_format_triggers = generic_format_triggers


generate_new_factory = package_factory
