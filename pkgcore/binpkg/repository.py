# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
binpkg ebuild repository
"""

__all__ = ("tree", "ConfiguredBinpkgTree", "force_unpacking")

import os

from pkgcore.repository import prototype, errors
from pkgcore.merge import triggers
from pkgcore.plugin import get_plugin
from pkgcore.ebuild.ebuild_built import pkg_uses_default_preinst
from pkgcore.config import ConfigHint
#needed to grab the PN
from pkgcore.ebuild.cpv import versioned_CPV
from pkgcore.ebuild.errors import InvalidCPV
from pkgcore.binpkg import repo_ops

from snakeoil.compatibility import raise_from
from snakeoil.currying import partial
from snakeoil.mappings import DictMixin, StackedDict
from snakeoil.osutils import listdir_dirs, listdir_files, access
from snakeoil.osutils import join as pjoin
from snakeoil.klass import jit_attr

from snakeoil.demandload import demandload
demandload(globals(),
    "pkgcore.merge:engine",
    "pkgcore.fs.livefs:scan",
    "snakeoil.data_source:local_source,data_source",
    "pkgcore.fs.contents:offset_rewriter,contentsSet",
    "pkgcore.repository:wrapper",
    "pkgcore.package:base@pkg_base",
    "pkgcore.ebuild:ebd",
    "errno",
    "pkgcore.fs.tar:generate_contents",
    "pkgcore.binpkg.xpak:Xpak",
    "pkgcore.util.bzip2:decompress",
    'pkgcore.binpkg:remote',
)


class force_unpacking(triggers.base):

    required_csets = ('new_cset',)
    priority = 5
    _hooks = ('sanity_check',)
    _label = 'forced decompression'
    _engine_type = triggers.INSTALLING_MODES

    def __init__(self, format_op):
        self.format_op = format_op

    def trigger(self, engine, cset):
        op = self.format_op
        op = getattr(op, 'install_op', op)
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
        fi = (x.change_attributes(data=local_source(
                pjoin(d, x.location.lstrip('/'))))
                for x in merge_cset.iterfiles())

        if engine.offset:
            # we're using merge_cset above, which has the final offset loc
            # pruned; this is required for the merge, however, we're updating
            # the cset so we have to insert the final offset back in.
            # wrap the iter, iow.
            fi = offset_rewriter(engine.offset, fi)

        cset = contentsSet(fi)

        # we *probably* should change the csets class at some point
        # since it no longer needs to be tar, but that's for another day.
        engine.replace_cset('new_cset', cset)


def wrap_factory(klass, *args, **kwds):

    class new_factory(klass):

        def _add_format_triggers(self, pkg, op_inst, format_op_inst,
                                 engine_inst):
            if engine.UNINSTALL_MODE != engine_inst.mode and \
                pkg == engine_inst.new and \
                pkg.repo is engine_inst.new.repo and \
                True:
#                not pkg_uses_default_preinst(pkg):
                t = force_unpacking(op_inst.format_op)
                t.register(engine_inst)

            klass._add_format_triggers(
                self, pkg, op_inst, format_op_inst, engine_inst)

        def scan_contents(self, location):
            return scan(location, offset=location)

    return new_factory(*args, **kwds)


class StackedXpakDict(DictMixin):
    __slots__ = ("_xpak", "_parent", "_pkg", "contents",
        "_wipes", "_mtime")

    _metadata_rewrites = {
        "depends":"DEPEND", "rdepends":"RDEPEND", "post_rdepends":"PDEPEND",
        "provides":"PROVIDE", "use":"USE", "eapi":"EAPI",
        "CONTENTS":"contents",
        }

    def __init__(self, parent, pkg):
        self._pkg = pkg
        self._parent = parent
        self._wipes = set()

    @jit_attr
    def xpak(self):
        return Xpak(self._parent._get_path(self._pkg))

    @jit_attr
    def mtime(self):
        return int(os.stat(self._parent._get_path(self._pkg)).st_mtime)

    def __getitem__(self, key):
        key = self._metadata_rewrites.get(key, key)
        if key in self._wipes:
            raise KeyError(self, key)
        if key == "contents":
            data = generate_contents(self._parent._get_path(self._pkg))
            object.__setattr__(self, "contents", data)
        elif key == "environment":
            data = self.xpak.get("environment.bz2")
            if data is None:
                data = data_source(self.xpak.get("environment"),
                    mutable=True)
                if data is None:
                    raise KeyError(
                        "environment.bz2 not found in xpak segment, "
                        "malformed binpkg?")
            else:
                data = data_source(decompress(data), mutable=True)
        elif key == "ebuild":
            data = self.xpak.get("%s-%s.ebuild" %
                (self._pkg.package, self._pkg.fullver), "")
            data = data_source(data)
        else:
            try:
                data = self.xpak[key]
            except KeyError:
                if key == '_eclasses_':
                    # hack...
                    data ={}
                else:
                    data = ''
        return data

    def __delitem__(self, key):
        if key in ("contents", "environment"):
            if key in self._wipes:
                raise KeyError(self, key)
            self._wipes.add(key)
        else:
            del self.xpak[key]

    def __setitem__(self, key, val):
        if key in ("contents", "environment"):
            setattr(self, key, val)
            self._wipes.discard(remove)
        else:
            self.xpak[key] = val
        return val

    def iterkeys(self):
        for k in self.xpak:
            yield k
        for k in ("environment", "contents"):
            if self.get(k) is not None:
                yield k

    def __contains__(self, key):
        translated_key = self._metadata_rewrites.get(key, key)
        if translated_key in self._wipes:
            return False
        elif key in ('ebuild', 'environment', 'contents'):
            return True
        return translated_key in self.xpak


class StackedCache(StackedDict):

    __externally_mutable__ = True

    def __delitem__(self, key):
        self._dicts[0].pop(key)


class tree(prototype.tree):

    format_magic = "ebuild_built"

    # yes, the period is required. no, do not try and remove it
    # (harring says it stays)
    extension = ".tbz2"

    configured = False
    configurables = ("settings",)
    operations_kls = repo_ops.operations
    cache_name = "Packages"

    pkgcore_config_type = ConfigHint({'location':'str',
        'repo_id':'str', 'ignore_paludis_versioning':'bool'}, typename='repo')

    def __init__(self, location, repo_id=None, ignore_paludis_versioning=False,
        cache_version='0'):
        """
        :param location: root of the tbz2 repository
        :keyword repo_id: unique repository id to use; else defaults to
            the location
        :keyword ignore_paludis_versioning: if False, error when -scm is seen.  If True,
            silently ignore -scm ebuilds
        """
        super(tree, self).__init__()
        self.base = location
        if repo_id is None:
            repo_id = location
        self.repo_id = repo_id
        self._versions_tmp_cache = {}
        self.ignore_paludis_versioning = ignore_paludis_versioning

        # XXX rewrite this when snakeoil.osutils grows an access equivalent.
        if not access(self.base, os.X_OK|os.R_OK):
            # either it doesn't exist, or we don't have perms.
            if not os.path.exists(self.base):
                raise errors.InitializationError(
                    "base %r doesn't exist: %s" % self.base)
            raise errors.InitializationError(
                "base directory %r with mode 0%03o isn't readable/executable"
                " by this user" % (self.base,
                os.stat(self.base).st_mode & 04777))

        self.cache = remote.get_cache_kls(cache_version)(pjoin(self.base, self.cache_name))
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
        except EnvironmentError, e:
            raise_from(KeyError("failed fetching categories: %s" % str(e)))

    def _get_packages(self, category):
        cpath = pjoin(self.base, category.lstrip(os.path.sep))
        l = set()
        d = {}
        lext = len(self.extension)
        bad = False
        try:
            for x in listdir_files(cpath):
                # don't use lstat; symlinks may exist
                if (x.endswith(".lockfile")
                    or not x[-lext:].lower() == self.extension or
                    x.startswith(".tmp.")):
                    continue
                pv = x[:-lext]
                try:
                    pkg = versioned_CPV(category+"/"+pv)
                except InvalidCPV:
                    bad = True
                if bad or not pkg.fullver:
                    if '-scm' in pv:
                        bad = 'scm'
                    elif '-try' in pv:
                        bad = 'try'
                    else:
                        raise InvalidCPV("%s/%s: no version component" %
                            (category, pv))
                    if self.ignore_paludis_versioning:
                        bad = False
                        continue
                    raise InvalidCPV("%s/%s: -%s version component is "
                        "not standard." % (category, pv, bad))
                l.add(pkg.package)
                d.setdefault((category, pkg.package), []).append(pkg.fullver)
        except EnvironmentError, e:
            raise_from(KeyError("failed fetching packages for category %s: %s" % \
            (pjoin(self.base, category.lstrip(os.path.sep)), str(e))))

        self._versions_tmp_cache.update(d)
        return tuple(l)

    def _get_versions(self, catpkg):
        return tuple(self._versions_tmp_cache.pop(catpkg))

    def _get_path(self, pkg):
        s = "%s-%s" % (pkg.package, pkg.fullver)
        return pjoin(self.base, pkg.category, s+".tbz2")

    _get_ebuild_path = _get_path

    def _get_metadata(self, pkg, force=False):
        xpak = StackedXpakDict(self, pkg)
        try:
            if force:
                raise KeyError
            cache_data = self.cache[pkg.cpvstr]
            if int(cache_data['mtime']) != int(xpak.mtime):
                raise KeyError
        except KeyError, ke:
            cache_data = self.cache.update_from_xpak(pkg, xpak)
        obj = StackedCache(cache_data, xpak)
        return obj

    def notify_add_package(self, pkg):
        prototype.tree.notify_add_package(self, pkg)
        # XXX horrible hack.
        self._get_metadata(self.match(pkg.versioned_atom)[0], force=True)
        self.cache.commit()

    def notify_remove_package(self, pkg):
        prototype.tree.notify_remove_package(self, pkg)
        try:
            os.rmdir(pjoin(self.base, pkg.category))
        except OSError, oe:
            if oe.errno != errno.ENOTEMPTY:
                raise
            del oe

    @property
    def _repo_ops(self):
        return repo_ops


class ConfiguredBinpkgTree(wrapper.tree):

    format_magic = "ebuild_built"
    configured = True

    def __init__(self, repo, domain_settings):
        # rebind to ourselves basically.

        class package_class(pkg_base.wrapper):

            _operations = self._generate_operations
            built = True
            __slots__ = ()

        wrapper.tree.__init__(self, repo, package_class=package_class)
        self.domain_settings = domain_settings

    def _generate_operations(self, domain, pkg, **kwargs):
        pkg = pkg._raw_pkg
        return ebd.built_operations(domain, pkg, initial_env=self.domain_settings,
            **kwargs)

tree.configure = ConfiguredBinpkgTree
