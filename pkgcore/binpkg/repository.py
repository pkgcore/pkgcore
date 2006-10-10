# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
binpkg ebuild repository
"""

import os, stat
from pkgcore.repository import prototype, errors

#needed to grab the PN
from pkgcore.ebuild.cpv import CPV as cpv
from pkgcore.util.currying import partial
from pkgcore.plugin import get_plugin
from pkgcore.util.mappings import DictMixin
from pkgcore.util.osutils import listdir_dirs, listdir_files
from pkgcore.binpkg.xpak import Xpak
from pkgcore.binpkg.tar import generate_contents
from pkgcore.util.bzip2 import decompress
from pkgcore.ebuild.ebuild_built import pkg_uses_default_preinst
from pkgcore.config import ConfigHint
from pkgcore.util.demandload import demandload
demandload(globals(),
           "pkgcore.merge:engine "
           "pkgcore.merge.triggers:SimpleTrigger "
           "pkgcore.fs.livefs:scan "
           "pkgcore.interfaces.data_source:data_source "
           "pkgcore.repository:wrapper "
           "pkgcore.package.mutated:MutatedPkg "
           "pkgcore.ebuild:ebd ")


def force_unpack_trigger(op, engine_inst, cset):
    op.setup_workdir()
    merge_contents = get_plugin("fs_ops.merge_contents")
    merge_contents(cset, offset=op.env["D"])
    cset.clear()
    cset.update(scan(op.env["D"], offset=op.env["D"]))

def generic_register(label, trigger, hook_name, triggers_list):
    for x in triggers_list:
        if x.label == label:
            break
    else:
        triggers_list.insert(0, trigger)


def wrap_factory(klass, *args, **kwds):

    class new_factory(klass):

        def _add_format_triggers(self, pkg, op_inst, format_op_inst,
                                 engine_inst):
            if engine.UNINSTALL_MODE != engine_inst.mode and \
                pkg == engine_inst.new and \
                not pkg_uses_default_preinst(pkg):

                label = "forced_decompression"
                t = SimpleTrigger("install",
                    partial(force_unpack_trigger, format_op_inst),
                    register_func=partial(generic_register, label),
                    label=label)
                engine_inst.add_triggers("sanity_check", t)

            klass._add_format_triggers(
                self, pkg, op_inst, format_op_inst, engine_inst)

        def scan_contents(self, location):
            return scan(location, offset=location)

    return new_factory(*args, **kwds)


class StackedXpakDict(DictMixin):
    __slots__ = ("_xpak", "_parent", "_pkg", "contents",
        "_wipes")

    _metadata_rewrites = {
        "depends":"DEPEND", "rdepends":"RDEPEND", "post_rdepends":"PDEPEND",
        "provides":"PROVIDE", "use":"USE", "eapi":"EAPI",
        "CONTENTS":"contents"}

    def __init__(self, parent, pkg):
        self._pkg = pkg
        self._parent = parent
        self._wipes = []
    
    def __getattr__(self, attr):
        if attr == "_xpak":
            data = Xpak(self._parent._get_path(self._pkg))
            object.__setattr__(self, attr, data)
            return data
        raise AttributeError(self, attr)
    
    def __getitem__(self, key):
        key = self._metadata_rewrites.get(key, key)
        if key in self._wipes:
            raise KeyError(self, key)
        if key == "contents":
            data = generate_contents(self._parent._get_path(self._pkg))
            object.__setattr__(self, "contents", data)
        elif key == "environment":
            data = self._xpak.get("environment.bz2", None)
            if data is None:
                data = data_source(self._xpak.get("environment", None), 
                    mutable=True)
                if data is None:
                    raise KeyError(
                        "environment.bz2 not found in xpak segment, "
                        "malformed binpkg?")
            else:
                data = data_source(decompress(data), mutable=True)
        elif key == "ebuild":
            data = self._xpak.get("%s-%s.ebuild" %
                (self._pkg.package, self._pkg.fullver), "")
            data = data_source(data)
        else:
            try:
                data = self._xpak[key]
            except KeyError:
                data =''
        return data
    
    def __delitem__(self, key):
        if key in ("contents", "environment"):
            if key in self._wipes:
                raise KeyError(self, key)
            self._wipes.append(key)
        else:
            del self._xpak[key]
    
    def __setitem__(self, key, val):
        if key in ("contents", "environment"):
            setattr(self, key, val)
            self._wipes = [x for x in self._wipes if x != key]
        else:
            self._xpak[key] = val
        return val
    
    def iterkeys(self):
        for k in self._xpak:
            yield k
        for k in ("environment", "contents"):
            if self.get(k, None) is not None:
                yield k


class tree(prototype.tree):

    format_magic = "ebuild_built"

    # yes, the period is required. no, do not try and remove it
    # (harring says it stays)
    extension = ".tbz2"

    configured = False
    configurables = ("settings", )

    pkgcore_config_type = ConfigHint(typename='repo')

    def __init__(self, location):
        super(tree, self).__init__()
        self.base = location
        self._versions_tmp_cache = {}
        try:
            st = os.lstat(self.base)
            if not stat.S_ISDIR(st.st_mode):
                raise errors.InitializationError(
                    "base not a dir: %s" % self.base)
            elif not st.st_mode & (os.X_OK|os.R_OK):
                raise errors.InitializationError(
                    "base lacks read/executable: %s" % self.base)

        except OSError:
            raise errors.InitializationError(
                "lstat failed on base %s" % self.base)

        self.package_class = wrap_factory(
            get_plugin("format." + self.format_magic), self)

    def _get_categories(self, *optional_category):
        # return if optional_category is passed... cause it's not yet supported
        if optional_category:
            return {}
        try:
            return tuple(
                x for x in listdir_dirs(self.base)
                if x.lower() != "all")
        except (OSError, IOError), e:
            raise KeyError("failed fetching categories: %s" % str(e))

    def _get_packages(self, category):
        cpath = os.path.join(self.base, category.lstrip(os.path.sep))
        l = set()
        d = {}
        lext = len(self.extension)
        try:
            for x in listdir_files(cpath):
                # don't use lstat; symlinks may exist
                if (x.endswith(".lockfile")
                    or not x[-lext:].lower() == self.extension):
                    continue
                x = cpv(category+"/"+x[:-lext])
                l.add(x.package)
                d.setdefault((category, x.package), []).append(x.fullver)
        except (OSError, IOError), e:
            raise KeyError("failed fetching packages for category %s: %s" % \
            (os.path.join(self.base, category.lstrip(os.path.sep)), str(e)))

        self._versions_tmp_cache.update(d)
        return tuple(l)

    def _get_versions(self, catpkg):
        return tuple(self._versions_tmp_cache.pop(catpkg))

    def _get_path(self, pkg):
        s = "%s-%s" % (pkg.package, pkg.fullver)
        return os.path.join(self.base, pkg.category, s+".tbz2")

    _get_ebuild_path = _get_path

    def _get_metadata(self, pkg):
        return StackedXpakDict(self, pkg)


class ConfiguredBinpkgTree(wrapper.tree):
    
    format_magic = "ebuild_built"
    configured = True
    
    def __init__(self, repo, domain_settings):
        # rebind to ourselves basically.
        def package_class(pkg):
            return MutatedPkg(pkg, 
                {"build":partial(self._generate_build_op, pkg)})
        wrapper.tree.__init__(self, repo, package_class=package_class)
        self.domain_settings = domain_settings

    def _generate_build_op(self, pkg, **kwargs):
        kwargs["initial_env"] = self.domain_settings
        kwargs["env_data_source"] = pkg.environment
        return ebd.binpkg_buildable(pkg, **kwargs)

tree.configure = ConfiguredBinpkgTree
