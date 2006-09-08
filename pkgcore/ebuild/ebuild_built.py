# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
built ebuild packages (vdb packages and binpkgs are derivatives of this)
"""

from pkgcore.ebuild import ebuild_src
from pkgcore.util.mappings import IndeterminantDict
from pkgcore.package import metadata
from pkgcore.interfaces.data_source import local_source
from pkgcore.fs import scan
from pkgcore.util.currying import post_curry
from pkgcore.ebuild.conditionals import DepSet
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild import ebd
from pkgcore.util.obj import DelayedInstantiation
from pkgcore.util.demandload import demandload
demandload(globals(),
           "pkgcore.merge:engine "
           "pkgcore.ebuild:triggers "
           "re ")

ebuild_triggers = triggers

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

    data = pkg.environment.get_fileobj().read()
    m = default_pkg_preinst_re.search(data)

    # second check. make sure there aren't two matches- if so, that
    # means we should not guess it.
    return m is not None and \
        default_pkg_preinst_re.search(data[m.end():]) is None

def wrap_inst(self, wrap, inst):
    return wrap(inst(self), self.use)

class package(ebuild_src.package):

    """
    built form of an ebuild
    """

    immutable = True
    tracked_attributes = ebuild_src.package.tracked_attributes[:]
    tracked_attributes.extend(["contents", "use", "environment"])
    allow_regen = False

    built = True

    _get_attr = dict(ebuild_src.package._get_attr)

    for x in ("_mtime_", "fetchables"):
        del _get_attr[x]
    del x

    _get_attr.update((x, post_curry(passthrough, x))
                     for x in ("contents", "environment", "ebuild"))
    _get_attr.update(
        (k, post_curry(wrap_inst,
                       ebuild_src.package._config_wrappables[k],
                       ebuild_src.package._get_attr[k]))
        for k in ebuild_src.package._config_wrappables
        if k in ebuild_src.package.tracked_attributes)

    _get_attr["use"] = lambda s:DelayedInstantiation(tuple,
        lambda: tuple(s.data["USE"].split()))
    _get_attr["depends"] = lambda s:DepSet("", atom)

    for x in ("maintainers", "longdescription", "herds"):
        locals()[x] = property(lambda s:None)
    del x

    def _update_metadata(self, pkg):
        raise NotImplementedError()

    def _repo_install_op(self, *args, **kwds):
        return self._parent._generate_format_install_op(self, *args, **kwds)

    def _repo_uninstall_op(self, *args, **kwds):
        return self._parent._generate_format_uninstall_op(self, *args, **kwds)

    def _repo_replace_op(self, *args, **kwds):
        return self._parent._generate_format_replace_op(self, *args, **kwds)

    def _fetch_metadata(self):
        return self._parent._get_metadata(self)

    def __str__(self):
        return "built ebuild: %s" % (self.cpvstr)

    def build(self):
        return self.repo.generate_buildop(self)

    def add_format_triggers(self, *args, **kwds):
        return self._parent._add_format_triggers(self, *args, **kwds)


def generic_format_triggers(self, pkg, op_inst, format_op_inst, engine_inst):
    if (engine_inst.mode in (engine.REPLACING_MODE, engine.INSTALL_MODE)
        and pkg == engine_inst.new):
        if not pkg_uses_default_preinst(pkg):
            engine_inst.add_triggers(
                "pre_merge",
                ebuild_triggers.preinst_contents_reset_trigger(format_op_inst))


def _generic_format_install_op(self, pkg, domain_settings):
    return ebd.install_op(pkg, initial_env=domain_settings,
                          env_data_source=pkg.environment)

def _generic_format_uninstall_op(self, pkg, domain_settings):
    return ebd.uninstall_op(pkg, initial_env=domain_settings,
                            env_data_source=pkg.environment)

def _generic_format_replace_op(self, pkg, domain_settings):
    return ebd.replace_op(pkg, initial_env=domain_settings,
                          env_data_source=pkg.environment)


class package_factory(metadata.factory):
    child_class = package

    def _get_metadata(self, pkg):
        return self._parent_repo._get_metadata(pkg)

    def new_package(self, cpv):
        inst = self._cached_instances.get(cpv, None)
        if inst is None:
            inst = self._cached_instances[cpv] = self.child_class(self,
                cpv)
        return inst

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

    def __del__(self):
        pass

    _forced_copy = ebuild_src.package.tracked_attributes

    def new_package(self, pkg, image_root, environment_path):
        self.pkg = pkg
        self.image_root = image_root
        self.environment_path = environment_path
        # lambda redirects path to environment path
        obj = self.child_class(self, pkg.cpvstr,
                               lambda *x:self.environment_path)
        for x in self._forced_copy:
            # bypass setattr restrictions.
            obj.__dict__[x] = getattr(self.pkg, x)
        obj.__dict__["use"] = self.pkg.use
        return obj

    def scan_contents(self, location):
        return scan(location, offset=location)

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
