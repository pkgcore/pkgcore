# Copyright: 2005-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
binpkg ebuild repository
"""

import os, stat

from pkgcore.repository import prototype, errors
from pkgcore.merge import triggers
from pkgcore.plugin import get_plugin
from pkgcore.ebuild.ebuild_built import pkg_uses_default_preinst
from pkgcore.config import ConfigHint
#needed to grab the PN
from pkgcore.ebuild.cpv import CPV as cpv

from snakeoil.currying import partial
from snakeoil.mappings import DictMixin
from snakeoil.osutils import listdir_dirs, listdir_files
from snakeoil.osutils import join as pjoin

from snakeoil.demandload import demandload
demandload(globals(),
    "pkgcore.merge:engine",
    "pkgcore.fs.livefs:scan",
    "pkgcore.interfaces.data_source:local_source",
    "pkgcore.fs.ops:offset_rewriter",
    "pkgcore.interfaces.data_source:data_source",
    "pkgcore.repository:wrapper",
    "pkgcore.package.mutated:MutatedPkg",
    "pkgcore.ebuild:ebd",
    "pkgcore.binpkg:repo_ops",
    "errno",
    "pkgcore.fs.tar:generate_contents",
    "pkgcore.binpkg.xpak:Xpak",
    "pkgcore.util.bzip2:decompress",
)


class force_unpacking(triggers.base):

    required_csets = ('install',)
    _hooks = ('sanity_check',)
    _priority = 5
    _label = 'forced decompression'
    _engine_type = triggers.INSTALLING_MODES

    def __init__(self, format_op):
        self.format_op = format_op

    def trigger(self, engine, cset):
        op = self.format_op
        op.setup_workdir()
        merge_contents = get_plugin("fs_ops.merge_contents")
        merge_cset = cset
        if engine.offset != '/':
            merge_cset = cset.change_offset(engine.offset, '/')
        merge_contents(merge_cset, offset=op.env["D"])

        # ok.  they're on disk.
        # now to avoid going back to the binpkg, we rewrite
        # the data_source for files to the on disk location.
        # we can update in place also, since we're not changing the mapping.

        # this rewrites the data_source to the ${D} loc.
        d = op.env["D"]
        fi = (x.change_attributes(data_source=local_source(
                pjoin(d, x.location.lstrip('/'))))
                for x in merge_cset.iterfiles())

        if engine.offset:
            # we're using merge_cset above, which has the final offset loc
            # pruned; this is required for the merge, however, we're updating
            # the cset so we have to insert the final offset back in.
            # wrap the iter, iow.
            fi = offset_rewriter(engine.offset, fi)

        # we *probably* should change the csets class at some point
        # since it no longer needs to be tar, but that's for another day.
        cset.update(fi)


def wrap_factory(klass, *args, **kwds):

    class new_factory(klass):

        def _add_format_triggers(self, pkg, op_inst, format_op_inst,
                                 engine_inst):
            if engine.UNINSTALL_MODE != engine_inst.mode and \
                pkg == engine_inst.new and \
                pkg.repo is engine_inst.new.repo and \
                not pkg_uses_default_preinst(pkg):
                t = force_unpacking(op_inst.install_op)
                t.register(engine_inst)

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
            data = self._xpak.get("environment.bz2")
            if data is None:
                data = data_source(self._xpak.get("environment"),
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
                data = ''
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
            if self.get(k) is not None:
                yield k


class tree(prototype.tree):

    format_magic = "ebuild_built"

    # yes, the period is required. no, do not try and remove it
    # (harring says it stays)
    extension = ".tbz2"

    configured = False
    configurables = ("settings",)

    pkgcore_config_type = ConfigHint({'location':'str',
        'repo_id':'str'}, typename='repo')

    def __init__(self, location, repo_id=None):
        super(tree, self).__init__()
        self.base = location
        if repo_id is None:
            repo_id = location
        self.repo_id = repo_id
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
        cpath = pjoin(self.base, category.lstrip(os.path.sep))
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
            (pjoin(self.base, category.lstrip(os.path.sep)), str(e)))

        self._versions_tmp_cache.update(d)
        return tuple(l)

    def _get_versions(self, catpkg):
        return tuple(self._versions_tmp_cache.pop(catpkg))

    def _get_path(self, pkg):
        s = "%s-%s" % (pkg.package, pkg.fullver)
        return pjoin(self.base, pkg.category, s+".tbz2")

    _get_ebuild_path = _get_path

    def _get_metadata(self, pkg):
        return StackedXpakDict(self, pkg)

    def notify_remove_package(self, pkg):
        prototype.tree.notify_remove_package(self, pkg)
        try:
            os.rmdir(pjoin(self.base, pkg.category))
        except OSError, oe:
            if oe.errno != errno.ENOTEMPTY:
                raise
            del oe

    def _install(self, pkg, *a, **kw):
        return repo_ops.install(self, pkg, *a, **kw)

    def _uninstall(self, pkg, *a, **kw):
        return repo_ops.uninstall(self, pkg, *a, **kw)

    def _replace(self, oldpkg, newpkg, *a, **kw):
        return repo_ops.replace(self, oldpkg, newpkg, *a, **kw)


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
