__all__ = ("tree", "ConfiguredTree")

import errno
import os
import stat
from functools import partial

from snakeoil import data_source
from snakeoil.fileutils import readfile
from snakeoil.mappings import IndeterminantDict
from snakeoil.osutils import listdir_dirs, pjoin

from ..config.hint import ConfigHint
from ..ebuild import ebuild_built
from ..ebuild.cpv import VersionedCPV
from ..ebuild.errors import InvalidCPV
from ..log import logger
from ..package import base as pkg_base
from ..repository import errors, prototype, wrapper
from . import repo_ops
from .contents import ContentsFile


class tree(prototype.tree):
    """Repository for packages installed on the filesystem."""

    livefs = True
    configured = False
    configurables = ("domain", "settings")
    configure = None
    package_factory = staticmethod(ebuild_built.generate_new_factory)
    operations_kls = repo_ops.operations

    pkgcore_config_type = ConfigHint(
        {'location': 'str',
         'cache_location': 'str', 'repo_id': 'str',
         'disable_cache': 'bool'},
        typename='repo')

    def __init__(self, location, cache_location=None, repo_id='vdb',
                 disable_cache=False):
        super().__init__(frozen=False)
        self.repo_id = repo_id
        self.location = location
        if disable_cache:
            cache_location = None
        elif cache_location is None:
            cache_location = pjoin("/var/cache/edb/dep", location.lstrip("/"))
        self.cache_location = cache_location
        self._versions_tmp_cache = {}
        try:
            st = os.stat(self.location)
            if not stat.S_ISDIR(st.st_mode):
                raise errors.InitializationError(
                    f"base not a dir: {self.location!r}")
            elif not st.st_mode & (os.X_OK|os.R_OK):
                raise errors.InitializationError(
                    f"base lacks read/executable: {self.location!r}")
        except FileNotFoundError:
            pass
        except OSError as e:
            raise errors.InitializationError(f'lstat failed on base: {self.location!r}') from e

        self.package_class = self.package_factory(self)

    def _get_categories(self, *optional_category):
        # return if optional_category is passed... cause it's not yet supported
        if optional_category:
            return {}
        try:
            try:
                return tuple(x for x in listdir_dirs(self.location) if not
                             x.startswith('.'))
            except EnvironmentError as e:
                raise KeyError(f"failed fetching categories: {e}") from e
        finally:
            pass

    def _get_packages(self, category):
        cpath = pjoin(self.location, category.lstrip(os.path.sep))
        l = set()
        d = {}
        bad = False
        try:
            for x in listdir_dirs(cpath):
                if x.startswith(".tmp.") or x.endswith(".lockfile") \
                        or x.startswith("-MERGING-"):
                    continue
                try:
                    pkg = VersionedCPV(f'{category}/{x}')
                except InvalidCPV:
                    bad = True
                if bad or not pkg.fullver:
                    if '-scm' in x:
                        bad = 'scm'
                    elif '-try' in x:
                        bad = 'try'
                    else:
                        raise InvalidCPV(f'{category}/{x}', 'no version component')
                    logger.error(
                        f'merged -{bad} pkg detected: {category}/{x}. '
                        f'throwing exception due to -{bad} not being a valid'
                        ' version component.  Silently ignoring that '
                        'specific version is not viable either since it '
                        'would result in pkgcore stomping whatever it was '
                        f'that -{bad} version merged.  '
                        'Use the offending pkg manager that merged it to '
                        'unmerge it.')
                    raise InvalidCPV(
                        f'{category}/{x}', f'{bad} version component is not standard.')
                l.add(pkg.package)
                d.setdefault((category, pkg.package), []).append(pkg.fullver)
        except EnvironmentError as e:
            category = pjoin(self.location, category.lstrip(os.path.sep))
            raise KeyError(f'failed fetching packages for category {category}: {e}') from e

        self._versions_tmp_cache.update(d)
        return tuple(l)

    def _get_versions(self, catpkg):
        return tuple(self._versions_tmp_cache.pop(catpkg))

    def _get_ebuild_path(self, pkg):
        s = f"{pkg.package}-{pkg.fullver}"
        return pjoin(self.location, pkg.category, s, s + ".ebuild")

    def _get_path(self, pkg):
        s = f"{pkg.package}-{pkg.fullver}"
        return pjoin(self.location, pkg.category, s)

    _metadata_rewrites = {
        "bdepend": "BDEPEND", "depend": "DEPEND", "rdepend": "RDEPEND", "pdepend": "PDEPEND",
        "use": "USE", "eapi": "EAPI", "CONTENTS": "contents",
        "source_repository": "repository", "fullslot": "SLOT",
    }

    def _get_metadata(self, pkg):
        return IndeterminantDict(
            partial(self._internal_load_key, pjoin(
                self.location, pkg.category,
                f"{pkg.package}-{pkg.fullver}")))

    def _internal_load_key(self, path, key):
        key = self._metadata_rewrites.get(key, key)
        if key == "contents":
            data = ContentsFile(pjoin(path, "CONTENTS"), mutable=True)
        elif key == "environment":
            fp = pjoin(path, key)
            if not os.path.exists(f'{fp}.bz2'):
                if not os.path.exists(fp):
                    # icky.
                    raise KeyError("environment: no environment file found")
                data = data_source.local_source(fp)
            else:
                data = data_source.bz2_source(f'{fp}.bz2')
        elif key == 'ebuild':
            fp = pjoin(path, os.path.basename(path.rstrip(os.path.sep)) + '.ebuild')
            data = data_source.local_source(fp)
        elif key == 'repo':
            # try both, for portage/paludis compatibility.
            data = readfile(pjoin(path, 'repository'), True)
            if data is None:
                data = readfile(pjoin(path, 'REPOSITORY'), True)
                if data is None:
                    raise KeyError(key)
        else:
            data = readfile(pjoin(path, key), True)
            if data is None:
                raise KeyError((path, key))
            data = data.rstrip('\n')
        return data

    def notify_remove_package(self, pkg):
        remove_it = len(self.packages[pkg.category]) == 1
        prototype.tree.notify_remove_package(self, pkg)
        if remove_it:
            try:
                os.rmdir(pjoin(self.location, pkg.category))
            except OSError as oe:
                # POSIX specifies either ENOTEMPTY or EEXIST for non-empty dir
                # in particular, Solaris uses EEXIST in that case.
                # https://github.com/pkgcore/pkgcore/pull/181
                if oe.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                    raise
                # silently swallow it;
                del oe

    def __str__(self):
        return f"{self.repo_id}: location {self.location}"


class _WrappedInstalledPkg(pkg_base.wrapper):
    """Installed package with configuration data bound to it."""

    built = True
    __slots__ = ()

    def __str__(self):
        return (
            f'installed pkg: {self.cpvstr}::{self.repo.repo_id}, '
            f'source repo {self.source_repository!r}'
        )


class ConfiguredTree(wrapper.tree, tree):
    """Configured repository for packages installed on the filesystem."""

    configured = True
    frozen_settable = False

    def __init__(self, vdb, domain, domain_settings):
        _WrappedInstalledPkg._operations = self._generate_operations
        _WrappedInstalledPkg.repo = self
        wrapper.tree.__init__(self, vdb, package_class=_WrappedInstalledPkg)
        self.domain = domain
        self.domain_settings = domain_settings

    def _generate_operations(self, domain, pkg, **kwargs):
        pkg = pkg._raw_pkg
        return ebd.built_operations(
            domain, pkg, initial_env=self.domain_settings, **kwargs)


tree.configure = ConfiguredTree
