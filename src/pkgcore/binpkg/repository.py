"""
binpkg ebuild repository
"""

__all__ = ("tree", "ConfiguredTree", "force_unpacking")

import errno
import os

from snakeoil import chksum, compression
from snakeoil.data_source import data_source, local_source
from snakeoil.klass import alias_attr, jit_attr, jit_attr_named
from snakeoil.mappings import DictMixin, StackedDict
from snakeoil.osutils import access, listdir_dirs, listdir_files, pjoin

from ..config.hint import ConfigHint
from ..ebuild import ebd, ebuild_built
from ..ebuild.cpv import VersionedCPV
from ..fs.contents import contentsSet, offset_rewriter
from ..fs.livefs import scan
from ..fs.tar import generate_contents
from ..merge import engine, triggers
from ..package import base as pkg_base
from ..plugin import get_plugin
from ..repository import errors, prototype, wrapper
from . import remote, repo_ops
from .xpak import Xpak


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

        cset.update(contentsSet(fi))

        # we *probably* should change the csets class at some point
        # since it no longer needs to be tar, but that's for another day.
        engine.replace_cset('new_cset', cset)


class BinPkg(ebuild_built.generate_new_factory):

    def _add_format_triggers(self, pkg, op_inst, format_op_inst,
                                engine_inst):
        if (engine.UNINSTALL_MODE != engine_inst.mode and
                pkg == engine_inst.new and pkg.repo is engine_inst.new.repo):
            t = force_unpacking(op_inst.format_op)
            t.register(engine_inst)

        klass._add_format_triggers(
            self, pkg, op_inst, format_op_inst, engine_inst)

    def scan_contents(self, location):
        return scan(location, offset=location)


class StackedXpakDict(DictMixin):
    __slots__ = ("_xpak", "_parent", "_pkg", "contents", "_wipes", "_chf_obj")

    _metadata_rewrites = {
        "bdepend": "BDEPEND",
        "depend": "DEPEND",
        "rdepend": "RDEPEND",
        "pdepend": "PDEPEND",
        "use": "USE",
        "eapi": "EAPI",
        "CONTENTS": "contents",
        "fullslot": "SLOT",
    }

    def __init__(self, parent, pkg):
        self._pkg = pkg
        self._parent = parent
        self._wipes = set()

    @jit_attr
    def xpak(self):
        return Xpak(self._parent._get_path(self._pkg))

    mtime = alias_attr('_chf_.mtime')

    @jit_attr_named('_chf_obj')
    def _chf_(self):
        return chksum.LazilyHashedPath(self._parent._get_path(self._pkg))

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
                data = data_source(self.xpak.get("environment"), mutable=True)
                if data is None:
                    raise KeyError(
                        "environment.bz2 not found in xpak segment, "
                        "malformed binpkg?")
            else:
                data = data_source(
                    compression.decompress_data('bzip2', data), mutable=True)
        elif key == "ebuild":
            data = self.xpak.get(f"{self._pkg.package}-{self._pkg.fullver}.ebuild", "")
            data = data_source(data)
        else:
            try:
                data = self.xpak[key]
            except KeyError:
                if key == '_eclasses_':
                    # hack...
                    data = {}
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
            self._wipes.discard(key)
        else:
            self.xpak[key] = val
        return val

    def keys(self):
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

    # yes, the period is required. no, do not try and remove it
    # (harring says it stays)
    extension = ".tbz2"

    configured = False
    configurables = ("settings",)
    operations_kls = repo_ops.operations
    cache_name = "Packages"

    pkgcore_config_type = ConfigHint({
        'location': 'str',
        'repo_id': 'str'},
        typename='repo')

    def __init__(self, location, repo_id=None, cache_version='0'):
        """
        :param location: root of the tbz2 repository
        :keyword repo_id: unique repository id to use; else defaults to
            the location
        """
        super().__init__()
        self.base = self.location = location
        if repo_id is None:
            repo_id = location
        self.repo_id = repo_id
        self._versions_tmp_cache = {}

        # XXX rewrite this when snakeoil.osutils grows an access equivalent.
        if not access(self.base, os.X_OK | os.R_OK):
            # either it doesn't exist, or we don't have perms.
            if not os.path.exists(self.base):
                raise errors.InitializationError(f"base {self.base!r} doesn't exist")
            raise errors.InitializationError(
                "base directory %r with mode 0%03o isn't readable/executable"
                " by this user" %
                (self.base, os.stat(self.base).st_mode & 0o4777))

        self.cache = remote.get_cache_kls(cache_version)(pjoin(self.base, self.cache_name))
        self.package_class = BinPkg(self)

    def __str__(self):
        return self.repo_id

    def _get_categories(self, *optional_category):
        # return if optional_category is passed... cause it's not yet supported
        if optional_category:
            return {}
        try:
            return tuple(
                x for x in listdir_dirs(self.base)
                if x.lower() != "all")
        except EnvironmentError as e:
            raise KeyError(f"failed fetching categories: {e}") from e

    def _get_packages(self, category):
        cpath = pjoin(self.base, category.lstrip(os.path.sep))
        l = set()
        d = {}
        lext = len(self.extension)
        bad = False
        try:
            for x in listdir_files(cpath):
                # don't use lstat; symlinks may exist
                if (x.endswith(".lockfile") or
                        not x[-lext:].lower() == self.extension or
                        x.startswith(".tmp.")):
                    continue
                pv = x[:-lext]
                pkg = VersionedCPV(f'{category}/{pv}')
                l.add(pkg.package)
                d.setdefault((category, pkg.package), []).append(pkg.fullver)
        except EnvironmentError as e:
            raise KeyError(
                "failed fetching packages for category %s: %s" %
                (pjoin(self.base, category.lstrip(os.path.sep)), str(e))) from e

        self._versions_tmp_cache.update(d)
        return tuple(l)

    def _get_versions(self, catpkg):
        return tuple(self._versions_tmp_cache.pop(catpkg))

    def _get_path(self, pkg):
        return pjoin(self.base, pkg.category, f"{pkg.package}-{pkg.fullver}.tbz2")

    _get_ebuild_path = _get_path

    def _get_metadata(self, pkg, force=False):
        xpak = StackedXpakDict(self, pkg)
        try:
            if force:
                raise KeyError
            cache_data = self.cache[pkg.cpvstr]
            if int(cache_data['mtime']) != int(xpak.mtime):
                raise KeyError
        except KeyError:
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
        except OSError as oe:
            # POSIX specifies either ENOTEMPTY or EEXIST for non-empty dir
            # in particular, Solaris uses EEXIST in that case.
            # https://github.com/pkgcore/pkgcore/pull/181
            if oe.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                raise
            del oe

    @property
    def _repo_ops(self):
        return repo_ops


class _WrappedBinpkg(pkg_base.wrapper):
    """Binary package with configuration data bound to it."""

    built = True
    __slots__ = ()

    def __str__(self):
        return (
            f'ebuild binary pkg: {self.cpvstr}::{self.repo.repo_id}, '
            f'source repo {self.source_repository!r}'
        )


class ConfiguredTree(wrapper.tree):
    """Configured repository for portage-compatible binary packages."""

    configured = True

    def __init__(self, repo, domain_settings):
        _WrappedBinpkg._operations = self._generate_operations
        _WrappedBinpkg.repo = self
        wrapper.tree.__init__(self, repo, package_class=_WrappedBinpkg)
        self.domain_settings = domain_settings

    def _generate_operations(self, domain, pkg, **kwargs):
        pkg = pkg._raw_pkg
        return ebd.built_operations(
            domain, pkg, initial_env=self.domain_settings, **kwargs)


tree.configure = ConfiguredTree
