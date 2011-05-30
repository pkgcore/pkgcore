# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
built ebuild packages (vdb packages and binpkgs are derivatives of this)
"""

__all__ = ("package", "package_factory")

from pkgcore.ebuild import ebuild_src, conditionals
from pkgcore.package import metadata
from snakeoil.data_source import local_source

from snakeoil.mappings import IndeterminantDict
from snakeoil.currying import post_curry, partial
from snakeoil.obj import DelayedInstantiation

from snakeoil.demandload import demandload
demandload(globals(),
    'pkgcore.merge:engine',
    'pkgcore.ebuild:triggers',
    're',
    'pkgcore.ebuild:ebd',
    'pkgcore.fs.livefs:scan',
)


def passthrough(inst, attr, rename=None):
    if rename is None:
        rename = attr
    return inst.data[rename]

def flatten_depset(inst, conditionals):
    return inst.evaluate_depset(conditionals)

default_pkg_preinst_re = None

def pkg_uses_default_preinst(pkg):
    global default_pkg_preinst_re
    if default_pkg_preinst_re is None:
        default_pkg_preinst_re = re.compile(
            "(?:^|\n)pkg_preinst *\(\)\s*{\s*return;?\s*}[ \t]*(?:\n|$)")

    data = pkg.environment.text_fileobj().read()
    m = default_pkg_preinst_re.search(data)

    # second check. make sure there aren't two matches- if so, that
    # means we should not guess it.
    return m is not None and \
        default_pkg_preinst_re.search(data[m.end():]) is None

def wrap_inst(self, wrap, inst):
    return wrap(inst(self), self.use)

_empty_fetchable = conditionals.DepSet.parse('', ebuild_src.fetchable,
    operators={})

class package(ebuild_src.base):

    """
    built form of an ebuild
    """

    immutable = True
    tracked_attributes = list(ebuild_src.package.tracked_attributes)
    tracked_attributes.extend(["contents", "use", "environment"])
    tracked_attributes = tuple(tracked_attributes)
    allow_regen = False

    # hack, not for consumer usage
    _is_from_source = False

    built = True

    __slots__ = ('cbuild', 'chost', 'ctarget', 'use', 'environment', 'contents')

    _get_attr = dict(ebuild_src.package._get_attr)

    _get_attr.update((x, post_curry(passthrough, x))
                     for x in ("contents", "environment", "ebuild"))
    _get_attr.update(
        (k, post_curry(wrap_inst,
                       ebuild_src.package._config_wrappables[k],
                       ebuild_src.package._get_attr[k]))
        for k in ebuild_src.package._config_wrappables
        if k in ebuild_src.package.tracked_attributes)

    _get_attr['fetchables'] = lambda self:_empty_fetchable

    _get_attr["use"] = lambda s:DelayedInstantiation(frozenset,
        lambda: frozenset(s.data["USE"].split()))

    def _chost_fallback(initial, self):
        o = self.data.get(initial)
        if o is None:
            o = self.data.get("CHOST")
            if o is None:
                return o
        return o.strip()

    _get_attr["cbuild"] = partial(_chost_fallback, 'CBUILD')
    _get_attr["chost"] = partial(_chost_fallback, 'CHOST')
    _get_attr["ctarget"] = partial(_chost_fallback, 'CTARGET')

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
        if not pkg_uses_default_preinst(pkg):
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

    _generate_format_install_op   = _generic_format_install_op
    _generate_format_uninstall_op = _generic_format_uninstall_op
    _generate_format_replace_op   = _generic_format_replace_op
    _add_format_triggers          = generic_format_triggers


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

    _forced_copy = ebuild_src.package.tracked_attributes

    def new_package(self, pkg, image_root, environment_path):
        self.pkg = pkg
        self.image_root = image_root
        self.environment_path = environment_path
        # lambda redirects path to environment path
        obj = self.child_class(self, pkg.cpvstr)
        for x in self._forced_copy:
            # bypass setattr restrictions.
            object.__setattr__(obj, x, getattr(self.pkg, x))
        object.__setattr__(obj, "use", self.pkg.use)
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
            except AttributeError:
                raise KeyError

    _generate_format_install_op   = _generic_format_install_op
    _generate_format_uninstall_op = _generic_format_uninstall_op
    _generate_format_replace_op   = _generic_format_replace_op
    _add_format_triggers          = generic_format_triggers


generate_new_factory = package_factory
