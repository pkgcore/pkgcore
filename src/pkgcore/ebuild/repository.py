"""
Ebuild repository, specific to gentoo ebuild trees.
"""

__all__ = ("UnconfiguredTree", "ConfiguredTree", "ProvidesRepo", "tree")

import locale
import os
import stat
from functools import partial, wraps
from itertools import chain, filterfalse
from operator import attrgetter
from random import shuffle
from sys import intern

from snakeoil import chksum, klass
from snakeoil.bash import iter_read_bash, read_dict
from snakeoil.containers import InvertedContains
from snakeoil.data_source import local_source
from snakeoil.fileutils import readlines
from snakeoil.mappings import ImmutableDict
from snakeoil.obj import make_kls
from snakeoil.osutils import listdir_dirs, listdir_files, pjoin
from snakeoil.sequences import iflatten_instance, stable_unique
from snakeoil.strings import pluralism as _pl
from snakeoil.weakrefs import WeakValCache

from .. import fetch
from ..config.hint import ConfigHint, configurable
from ..fs.livefs import sorted_scan
from ..log import logger
from ..operations import repo as _repo_ops
from ..package import errors as pkg_errors
from ..repository import configured, errors, prototype, util
from ..repository.virtual import RestrictionRepo
from ..restrictions import packages
from ..util.packages import groupby_pkg
from . import atom, cpv, digest, ebd, ebuild_src
from . import eclass_cache as eclass_cache_mod
from . import errors as ebuild_errors
from . import processor, repo_objs, restricts
from .eapi import get_eapi


class repo_operations(_repo_ops.operations):

    def _cmd_implementation_digests(self, domain, matches, observer,
                                    mirrors=False, force=False):
        manifest_config = self.repo.config.manifests
        if manifest_config.disabled:
            observer.info(f"repo {self.repo.repo_id} has manifests disabled")
            return
        required_chksums = set(manifest_config.required_hashes)
        write_chksums = manifest_config.hashes
        distdir = domain.fetcher.distdir
        ret = set()

        for key_query in sorted(set(match.unversioned_atom for match in matches)):
            pkgs = self.repo.match(key_query)

            # check for pkgs masked by bad metadata
            bad_metadata = self.repo._bad_masked.match(key_query)
            if bad_metadata:
                for pkg in bad_metadata:
                    e = pkg.data
                    error_str = f"{pkg.cpvstr}: {e.msg(verbosity=observer.verbosity)}"
                    observer.error(error_str)
                    ret.add(key_query)
                continue

            # Check for bad ebuilds -- mismatched or invalid PNs won't be
            # matched by regular restrictions so they will otherwise be
            # ignored.
            ebuilds = {
                x for x in listdir_files(pjoin(self.repo.location, str(key_query)))
                if x.endswith('.ebuild')
            }
            unknown_ebuilds = ebuilds.difference(os.path.basename(x.path) for x in pkgs)
            if unknown_ebuilds:
                error_str = (
                    f"{key_query}: invalid ebuild{_pl(unknown_ebuilds)}: "
                    f"{', '.join(unknown_ebuilds)}"
                )
                observer.error(error_str)
                ret.add(key_query)
                continue

            # empty package dir
            if not pkgs:
                continue

            manifest = pkgs[0].manifest

            # all pkgdir fetchables
            pkgdir_fetchables = {}
            for pkg in pkgs:
                pkgdir_fetchables.update({
                    fetchable.filename: fetchable for fetchable in
                    iflatten_instance(pkg.generate_fetchables(
                        allow_missing_checksums=True,
                        skip_default_mirrors=(not mirrors)),
                        fetch.fetchable)
                })

            # fetchables targeted for (re-)manifest generation
            fetchables = {}
            chksum_set = set(write_chksums)
            for filename, fetchable in pkgdir_fetchables.items():
                if force or not required_chksums.issubset(fetchable.chksums):
                    fetchable.chksums = {
                        k: v for k, v in fetchable.chksums.items() if k in chksum_set}
                    fetchables[filename] = fetchable

            # Manifest files aren't necessary with thin manifests and no distfiles
            if manifest_config.thin and not pkgdir_fetchables:
                if os.path.exists(manifest.path):
                    try:
                        os.remove(manifest.path)
                    except EnvironmentError as e:
                        observer.error(
                            'failed removing old manifest: '
                            f'{key_query}::{self.repo.repo_id}: {e}')
                        ret.add(key_query)
                continue

            # Manifest file is current and not forcing a refresh
            if not force and manifest.distfiles.keys() == pkgdir_fetchables.keys():
                continue

            pkg_ops = domain.pkg_operations(pkgs[0], observer=observer)
            if not pkg_ops.supports("fetch"):
                observer.error(f"pkg {pkg} doesn't support fetching, can't generate manifest")
                ret.add(key_query)
                continue

            # fetch distfiles
            if not pkg_ops.fetch(list(fetchables.values()), observer):
                ret.add(key_query)
                continue

            # calculate checksums for fetched distfiles
            try:
                for fetchable in fetchables.values():
                    chksums = chksum.get_chksums(
                        pjoin(distdir, fetchable.filename), *write_chksums)
                    fetchable.chksums = dict(zip(write_chksums, chksums))
            except chksum.MissingChksumHandler as e:
                observer.error(f'failed generating chksum: {e}')
                ret.add(key_query)
                break

            if key_query not in ret:
                fetchables.update(pkgdir_fetchables)
                observer.info(f"generating manifest: {key_query}::{self.repo.repo_id}")
                manifest.update(sorted(fetchables.values()), chfs=write_chksums)

        return ret


def _sort_eclasses(config, repo_config):
    repo_path = repo_config.location
    repo_id = repo_config.repo_id
    masters = repo_config.masters
    eclasses = []

    default = config.get_default('repo_config')
    if repo_config._missing_masters and default is not None:
        # use default repo's eclasses for overlays with missing masters
        location = default.location
    else:
        location = repo_path

    if not masters:
        eclasses = [location]
    else:
        repo_map = {
            r.repo_id: r.location for r in
            config.objects['repo_config'].values()}
        eclasses = [repo_map[x] for x in masters]

    # add the repo's eclass directories if it's not specified.
    # do it in this fashion so that the repo's masters can actually interpose
    # this repo's eclasses in between others.
    # admittedly an odd thing to do, but it has some benefits
    if repo_path not in eclasses:
        eclasses.append(repo_path)

    eclasses = [eclass_cache_mod.cache(pjoin(x, 'eclass'), location=location)
                for x in eclasses]

    if len(eclasses) == 1:
        eclasses = eclasses[0]
    else:
        eclasses = list(reversed(eclasses))
        eclasses = eclass_cache_mod.StackedCaches(
            eclasses, location=location, eclassdir=location)
    return eclasses


class ProvidesRepo(util.SimpleTree):
    """Fake, installed repo populated with entries from package.provided."""

    class PkgProvidedParent:

        def __init__(self, **kwds):
            self.__dict__.update(kwds)

    class PkgProvided(ebuild_src.base):

        __slots__ = ('use',)

        package_is_real = False
        __inst_caching__ = True

        @property
        def keywords(self):
            return InvertedContains(())

        def __init__(self, *a, **kwds):
            super().__init__(*a, **kwds)
            object.__setattr__(self, "use", [])
            object.__setattr__(self, "data", {"SLOT": "0"})
            object.__setattr__(self, "eapi", get_eapi('0'))

    def __init__(self, pkgs, repo_id='package.provided'):
        d = {}
        for pkg in pkgs:
            d.setdefault(pkg.category, {}).setdefault(pkg.package, []).append(pkg.fullver)
        intermediate_parent = self.PkgProvidedParent()
        super().__init__(
            d, pkg_klass=partial(self.PkgProvided, intermediate_parent),
            livefs=True, frozen=True, repo_id=repo_id)
        intermediate_parent._parent_repo = self

        if not d:
            self.match = self.itermatch = self._empty_provides_iterable
            self.has_match = self._empty_provides_has_match

    @staticmethod
    def _empty_provides_iterable(*args, **kwds):
        return iter(())

    @staticmethod
    def _empty_provides_has_match(*args, **kwds):
        return False


@configurable(
    typename='repo',
    types={
        'repo_config': 'ref:repo_config', 'cache': 'refs:cache',
        'eclass_cache': 'ref:eclass_cache',
        'default_mirrors': 'list',
        'allow_missing_manifests': 'bool'},
    requires_config='config')
def tree(config, repo_config, cache=(), eclass_cache=None,
         default_mirrors=None, allow_missing_manifests=False):
    """Initialize an unconfigured ebuild repository."""
    repo_id = repo_config.repo_id
    repo_path = repo_config.location

    if repo_config.masters is None:
        # if it's None, that means it's not a standalone, and is PMS, or misconfigured.
        # empty tuple means it's a standalone repository
        default = config.get_default('repo_config')
        if default is None:
            raise errors.InitializationError(
                f"repo {repo_id!r} at {repo_path!r} requires missing default repo")

    configured_repos = tuple(r.repo_id for r in config.objects['repo_config'].values())
    missing = set(repo_config.masters).difference(configured_repos)
    if missing:
        missing = ', '.join(map(repr, sorted(missing)))
        raise errors.InitializationError(
            f'repo {repo_id!r} at path {repo_path!r} has missing masters: {missing}')

    try:
        masters = tuple(config.objects['repo'][r] for r in repo_config.masters)
    except RecursionError:
        repo_id = repo_config.repo_id
        masters = ', '.join(repo_config.masters)
        raise errors.InitializationError(
            f'{repo_id!r} repo has cyclic masters: {masters}')

    if eclass_cache is None:
        eclass_cache = _sort_eclasses(config, repo_config)

    return UnconfiguredTree(
        repo_config.location, eclass_cache=eclass_cache, masters=masters, cache=cache,
        default_mirrors=default_mirrors,
        allow_missing_manifests=allow_missing_manifests,
        repo_config=repo_config)


class UnconfiguredTree(prototype.tree):
    """Raw implementation supporting standard ebuild tree.

    Return packages don't have USE configuration bound to them.
    """

    false_packages = frozenset(["CVS", ".svn"])
    false_categories = frozenset([
        "eclass", "profiles", "packages", "distfiles", "metadata",
        "licenses", "scripts", "CVS", "local"])
    configured = False
    configurables = ("domain", "settings")
    configure = None
    package_factory = staticmethod(ebuild_src.generate_new_factory)
    enable_gpg = False
    extension = '.ebuild'

    operations_kls = repo_operations

    pkgcore_config_type = ConfigHint({
        'location': 'str',
        'eclass_cache': 'ref:eclass_cache',
        'masters': 'refs:repo',
        'cache': 'refs:cache',
        'default_mirrors': 'list',
        'allow_missing_manifests': 'bool',
        'repo_config': 'ref:repo_config',
        },
        typename='repo')

    def __init__(self, location, eclass_cache=None, masters=(), cache=(),
                 default_mirrors=None, allow_missing_manifests=False, package_cache=True,
                 repo_config=None):
        """
        :param location: on disk location of the tree
        :param cache: sequence of :obj:`pkgcore.cache.template.database` instances
            to use for storing metadata
        :param masters: repo masters this repo inherits from
        :param eclass_cache: If not None, :obj:`pkgcore.ebuild.eclass_cache`
            instance representing the eclasses available,
            if None, generates the eclass_cache itself
        :param default_mirrors: Either None, or sequence of mirrors to try
            fetching from first, then falling back to other uri
        :param package_cache: boolean controlling package instance caching
        :param repo_config: :obj:`pkgcore.repo_objs.RepoConfig` instance for the related repo
        """
        super().__init__()
        self.base = self.location = location
        self.package_cache = package_cache
        if repo_config is None:
            repo_config = repo_objs.RepoConfig(location)
        self.config = repo_config

        # profiles dir is required by PMS
        if not os.path.isdir(self.config.profiles_base):
            raise errors.InvalidRepo(f'missing required profiles dir: {self.location!r}')

        # verify we support the repo's EAPI
        if not self.is_supported:
            raise errors.UnsupportedRepo(self)

        if eclass_cache is None:
            eclass_cache = eclass_cache_mod.cache(
                pjoin(self.location, 'eclass'), location=self.location)
        self.eclass_cache = eclass_cache

        self.masters = masters
        self.trees = tuple(masters) + (self,)
        self.licenses = repo_objs.Licenses(self.location)
        self.profiles = self.config.profiles
        if masters:
            self.licenses = repo_objs.OverlayedLicenses(*self.trees)
            self.profiles = repo_objs.OverlayedProfiles(*self.trees)

        # use mirrors from masters if not defined in the repo
        mirrors = dict(self.thirdpartymirrors)
        for master in masters:
            for k, v in master.mirrors.items():
                if k not in mirrors:
                    mirrors[k] = v

        if isinstance(cache, (tuple, list)):
            cache = tuple(cache)
        else:
            cache = (cache,)

        self.mirrors = mirrors
        self.default_mirrors = default_mirrors
        self.cache = cache
        self._allow_missing_chksums = allow_missing_manifests
        self.package_class = self.package_factory(
            self, cache, self.eclass_cache, self.mirrors, self.default_mirrors)
        self._shared_pkg_cache = WeakValCache()
        self._bad_masked = RestrictionRepo(repo_id='bad_masked')
        self.projects_xml = repo_objs.LocalProjectsXml(
            pjoin(self.location, 'metadata', 'projects.xml'))

    repo_id = klass.alias_attr("config.repo_id")
    repo_name = klass.alias_attr("config.repo_name")
    aliases = klass.alias_attr("config.aliases")
    eapi = klass.alias_attr('config.eapi')
    is_supported = klass.alias_attr('config.eapi.is_supported')
    pkg_masks = klass.alias_attr('config.pkg_masks')

    @klass.jit_attr
    def known_arches(self):
        """Return all known arches for a repo (including masters)."""
        return frozenset(chain.from_iterable(
            r.config.known_arches for r in self.trees))

    def path_restrict(self, path):
        """Return a restriction from a given path in a repo.

        :param path: full or partial path to an ebuild
        :return: a package restriction matching the given path if possible
        :raises ValueError: if the repo doesn't contain the given path, the
            path relates to a file that isn't an ebuild, or the ebuild isn't in the
            proper directory layout
        """
        if path not in self:
            raise ValueError(f"{self.repo_id!r} repo doesn't contain: {path!r}")

        if not path.startswith(os.sep) and os.path.exists(pjoin(self.location, path)):
            path_chunks = path.split(os.path.sep)
        else:
            path = os.path.realpath(os.path.abspath(path))
            relpath = path[len(os.path.realpath(self.location)):].strip('/')
            path_chunks = relpath.split(os.path.sep)

        if os.path.isfile(path):
            if not path.endswith('.ebuild'):
                raise ValueError(f"file is not an ebuild: {path!r}")
            elif len(path_chunks) != 3:
                # ebuild isn't in a category/PN directory
                raise ValueError(
                    f"ebuild not in the correct directory layout: {path!r}")

        restrictions = []

        # add restrictions until path components run out
        try:
            restrictions.append(restricts.RepositoryDep(self.repo_id))
            if path_chunks[0] in self.categories:
                restrictions.append(restricts.CategoryDep(path_chunks[0]))
                restrictions.append(restricts.PackageDep(path_chunks[1]))
                base = cpv.VersionedCPV(f"{path_chunks[0]}/{os.path.splitext(path_chunks[2])[0]}")
                restrictions.append(restricts.VersionMatch('=', base.version, rev=base.revision))
        except IndexError:
            pass
        return packages.AndRestriction(*restrictions)

    def __getitem__(self, cpv):
        cpv_inst = self.package_class(*cpv)
        if cpv_inst.fullver not in self.versions[(cpv_inst.category, cpv_inst.package)]:
            raise KeyError(cpv)
        return cpv_inst

    def rebind(self, **kwds):
        """Generate a new tree instance with the same location using new keywords.

        :param kwds: see __init__ for valid values
        """
        o = self.__class__(self.location, **kwds)
        o.categories = self.categories
        o.packages = self.packages
        o.versions = self.versions
        return o

    @klass.jit_attr
    def thirdpartymirrors(self):
        mirrors = {}
        fp = pjoin(self.location, 'profiles', 'thirdpartymirrors')
        try:
            for k, v in read_dict(fp, splitter=None).items():
                v = v.split()
                # shuffle mirrors so the same ones aren't used every time
                shuffle(v)
                mirrors[k] = v
        except FileNotFoundError:
            pass
        return ImmutableDict(mirrors)

    @klass.jit_attr
    def category_dirs(self):
        try:
            return frozenset(map(intern, filterfalse(
                self.false_categories.__contains__,
                (x for x in listdir_dirs(self.base) if not x.startswith('.')))))
        except EnvironmentError as e:
            logger.error(f"failed listing categories: {e}")
        return ()

    def _get_categories(self, *optional_category):
        # why the auto return? current porttrees don't allow/support
        # categories deeper then one dir.
        if optional_category:
            # raise KeyError
            return ()
        categories = frozenset(chain.from_iterable(repo.config.categories for repo in self.trees))
        if categories:
            return categories
        return self.category_dirs

    def _get_packages(self, category):
        cpath = pjoin(self.base, category.lstrip(os.path.sep))
        try:
            return tuple(filterfalse(
                self.false_packages.__contains__, listdir_dirs(cpath)))
        except FileNotFoundError:
            if category in self.categories:
                # ignore it, since it's PMS mandated that it be allowed.
                return ()
        except EnvironmentError as e:
            category = pjoin(self.base, category.lstrip(os.path.sep))
            raise KeyError(
                f'failed fetching packages for category {category}: {e}') from e

    def _get_versions(self, catpkg):
        """Determine available versions for a given package.

        Ebuilds with mismatched or invalid package names are ignored.
        """
        cppath = pjoin(self.base, catpkg[0], catpkg[1])
        pkg = f'{catpkg[-1]}-'
        lp = len(pkg)
        extension = self.extension
        ext_len = -len(extension)
        try:
            return tuple(
                x[lp:ext_len] for x in listdir_files(cppath)
                if x[ext_len:] == extension and x[:lp] == pkg)
        except EnvironmentError as e:
            raise KeyError(
                "failed fetching versions for package %s: %s" %
                (pjoin(self.base, '/'.join(catpkg)), str(e))) from e

    def _pkg_filter(self, raw, error_callback, pkgs):
        """Filter packages with bad metadata."""
        while True:
            try:
                pkg = next(pkgs)
            except pkg_errors.PackageError:
                # ignore pkgs with invalid CPVs
                continue
            except StopIteration:
                return

            if raw:
                yield pkg
            elif self._bad_masked.has_match(pkg.versioned_atom) and error_callback is not None:
                error_callback(self._bad_masked[pkg.versioned_atom])
            else:
                # check pkgs for unsupported/invalid EAPIs and bad metadata
                try:
                    if not pkg.is_supported:
                        exc = pkg_errors.MetadataException(
                            pkg, 'eapi', f"EAPI '{pkg.eapi}' is not supported")
                        self._bad_masked[pkg.versioned_atom] = exc
                        if error_callback is not None:
                            error_callback(exc)
                        continue
                    # TODO: add a generic metadata validation method to avoid slow metadata checks?
                    pkg.data
                    pkg.slot
                    pkg.required_use
                except pkg_errors.MetadataException as e:
                    self._bad_masked[e.pkg.versioned_atom] = e
                    if error_callback is not None:
                        error_callback(e)
                    continue
                yield pkg

    def itermatch(self, *args, **kwargs):
        raw = 'raw_pkg_cls' in kwargs or not kwargs.get('versioned', True)
        error_callback = kwargs.pop('error_callback', None)
        kwargs.setdefault('pkg_filter', partial(self._pkg_filter, raw, error_callback))
        return super().itermatch(*args, **kwargs)

    def _get_ebuild_path(self, pkg):
        return pjoin(
            self.base, pkg.category, pkg.package,
            f"{pkg.package}-{pkg.fullver}{self.extension}")

    def _get_ebuild_src(self, pkg):
        return local_source(self._get_ebuild_path(pkg), encoding='utf8')

    def _get_shared_pkg_data(self, category, package):
        key = (category, package)
        o = self._shared_pkg_cache.get(key)
        if o is None:
            mxml = self._get_metadata_xml(category, package)
            manifest = self._get_manifest(category, package)
            o = repo_objs.SharedPkgData(mxml, manifest)
            self._shared_pkg_cache[key] = o
        return o

    def _get_metadata_xml(self, category, package):
        return repo_objs.LocalMetadataXml(pjoin(
            self.base, category, package, "metadata.xml"))

    def _get_manifest(self, category, package):
        return digest.Manifest(pjoin(
            self.base, category, package, "Manifest"),
            thin=self.config.manifests.thin,
            enforce_gpg=self.enable_gpg)

    def _get_digests(self, pkg, allow_missing=False):
        if self.config.manifests.disabled:
            return True, {}
        try:
            manifest = pkg._shared_pkg_data.manifest
            manifest.allow_missing = allow_missing
            return allow_missing, manifest.distfiles
        except pkg_errors.ParseChksumError as e:
            if e.missing and allow_missing:
                return allow_missing, {}
            raise pkg_errors.MetadataException(pkg, 'manifest', str(e))

    def __repr__(self):
        return "<ebuild %s location=%r @%#8x>" % (
            self.__class__.__name__, self.base, id(self))

    @klass.jit_attr
    def deprecated(self):
        """Base deprecated packages restriction from profiles/package.deprecated."""
        return packages.OrRestriction(*self.config.pkg_deprecated)

    def _regen_operation_helper(self, **kwds):
        return _RegenOpHelper(
            self, force=bool(kwds.get('force', False)),
            eclass_caching=bool(kwds.get('eclass_caching', True)))

    def __getstate__(self):
        d = self.__dict__.copy()
        del d['_shared_pkg_cache']
        return d

    def __setstate__(self, state):
        self.__dict__ = state.copy()
        self.__dict__['_shared_pkg_cache'] = WeakValCache()


class _RegenOpHelper:

    def __init__(self, repo, force=False, eclass_caching=True):
        self.force = force
        self.eclass_caching = eclass_caching
        self.ebp = self.request_ebp()

    def request_ebp(self):
        ebp = processor.request_ebuild_processor()
        if self.eclass_caching:
            ebp.allow_eclass_caching()
        return ebp

    def __call__(self, pkg):
        try:
            return pkg._fetch_metadata(ebp=self.ebp, force_regen=self.force)
        except pkg_errors.MetadataException as e:
            # ebuild processor is dead, so force a replacement request
            self.ebp = self.request_ebp()
            raise

    def __del__(self):
        if self.eclass_caching:
            self.ebp.disable_eclass_caching()
        processor.release_ebuild_processor(self.ebp)


class ConfiguredTree(configured.tree):
    """Wrapper around a :obj:`UnconfiguredTree` binding build/configuration data (USE)."""

    configurable = "use"
    config_wrappables = {
        x: klass.alias_method("evaluate_depset")
        for x in (
            "bdepend", "depend", "rdepend", "pdepend",
            "fetchables", "license", "src_uri", "restrict", "required_use",
        )
    }

    def __init__(self, raw_repo, domain, domain_settings, fetcher=None):
        """
        :param raw_repo: :obj:`UnconfiguredTree` instance
        :param domain_settings: environment settings to bind
        :param fetcher: :obj:`pkgcore.fetch.base.fetcher` instance to use
            for getting access to fetchable files
        """
        required_settings = {'USE', 'CHOST'}
        missing_settings = required_settings.difference(domain_settings)
        if missing_settings:
            raise errors.InitializationError(
                f"{self.__class__} missing required setting{_pl(missing_settings)}: "
                f"{', '.join(map(repr, missing_settings))}")

        chost = domain_settings['CHOST']
        scope_update = {'chost': chost}
        scope_update.update(
            (x, domain_settings.get(x.upper(), chost))
            for x in ('cbuild', 'ctarget'))
        scope_update.update(
            (x, domain_settings.get(x.upper(), ''))
            for x in ('cflags', 'cxxflags', 'ldflags'))
        scope_update['operations_callback'] = self._generate_pkg_operations

        # update wrapped attr funcs requiring access to the class instance
        for k, v in self.config_wrappables.items():
            if isinstance(v, str):
                self.config_wrappables[k] = getattr(self, v)

        super().__init__(
            raw_repo, self.config_wrappables, pkg_kls_injections=scope_update)

        self.domain = domain
        self.domain_settings = domain_settings
        self._fetcher_override = fetcher
        self._delayed_iuse = partial(make_kls(InvertedContains), InvertedContains)

    def _wrap_attr(config_wrappables):
        """Register wrapped attrs that require class instance access."""
        def _wrap_func(func):
            @wraps(func)
            def wrapped(*args, **kwargs):
                return func(*args, **kwargs)
            attr = func.__name__.lstrip('_')
            config_wrappables[attr] = func.__name__
            return wrapped
        return _wrap_func

    @_wrap_attr(config_wrappables)
    def _iuse_effective(self, raw_pkg_iuse_effective, _enabled_use, pkg):
        """IUSE_EFFECTIVE for a package."""
        profile_iuse_effective = self.domain.profile.iuse_effective
        return frozenset(profile_iuse_effective.union(raw_pkg_iuse_effective))

    @_wrap_attr(config_wrappables)
    def _distfiles(self, raw_pkg_distfiles, enabled_use, pkg):
        """Distfiles used by a package."""
        return tuple(stable_unique(raw_pkg_distfiles.evaluate_depset(enabled_use)))

    @_wrap_attr(config_wrappables)
    def _user_patches(self, _raw_pkg_patches, _enabled_use, pkg):
        """User patches that will be applied when building a package."""
        # determine available user patches for >= EAPI 6
        if pkg.eapi.options.user_patches:
            patches = []
            patchroot = pjoin(self.domain.config_dir, 'patches')
            patch_dirs = [
                pkg.PF,
                f'{pkg.PF}:{pkg.slot}',
                pkg.P,
                f'{pkg.P}:{pkg.slot}',
                pkg.PN,
                f'{pkg.PN}:{pkg.slot}',
            ]
            for d in patch_dirs:
                for root, _dirs, files in os.walk(pjoin(patchroot, pkg.category, d)):
                    files = (
                        pjoin(root, f) for f in sorted(files, key=locale.strxfrm)
                        if f.endswith(('.diff', '.patch')))
                    patches.append((root, tuple(files)))
            return tuple(patches)
        return None

    def _get_delayed_immutable(self, pkg, immutable):
        return InvertedContains(set(pkg.iuse).difference(immutable))

    def _get_pkg_kwds(self, pkg):
        immutable, enabled, _disabled = self.domain.get_package_use_unconfigured(pkg)
        return {
            "initial_settings": enabled,
            "unchangable_settings": self._delayed_iuse(
                self._get_delayed_immutable, pkg, immutable)}

    def _generate_pkg_operations(self, domain, pkg, **kwds):
        fetcher = self._fetcher_override
        if fetcher is None:
            fetcher = domain.fetcher
        return ebd.src_operations(
            domain, pkg, pkg.repo.eclass_cache, fetcher=fetcher, **kwds)


UnconfiguredTree.configure = ConfiguredTree
