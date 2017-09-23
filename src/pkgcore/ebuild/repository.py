# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
Ebuild repository, specific to gentoo ebuild trees.
"""

__all__ = ("tree",)

from functools import partial, wraps
from itertools import imap, ifilterfalse
import os
import stat

from snakeoil import klass
from snakeoil.bash import iter_read_bash, read_dict
from snakeoil.compatibility import intern, raise_from
from snakeoil.containers import InvertedContains
from snakeoil.demandload import demandload
from snakeoil.fileutils import readlines
from snakeoil.obj import make_kls
from snakeoil.osutils import listdir_files, listdir_dirs, pjoin
from snakeoil.weakrefs import WeakValCache

from pkgcore.config import ConfigHint, configurable
from pkgcore.ebuild import ebuild_src
from pkgcore.ebuild import eclass_cache as eclass_cache_module
from pkgcore.operations import repo as _repo_ops
from pkgcore.repository import prototype, errors, configured

demandload(
    'errno',
    'locale',
    'operator:attrgetter',
    'random:shuffle',
    'snakeoil.chksum:get_chksums',
    'snakeoil.data_source:local_source',
    'snakeoil.sequences:iflatten_instance',
    'pkgcore:fetch',
    'pkgcore.ebuild:cpv,digest,ebd,repo_objs,atom,restricts,profiles,processor',
    'pkgcore.ebuild:errors@ebuild_errors',
    'pkgcore.fs.livefs:sorted_scan',
    'pkgcore.package:errors@pkg_errors',
    'pkgcore.restrictions:packages',
    'pkgcore.util.packages:groupby_pkg',
)


class repo_operations(_repo_ops.operations):

    def _cmd_implementation_digests(self, domain, matches, observer,
                                    mirrors=False, force=False):
        manifest_config = self.repo.config.manifests
        if manifest_config.disabled:
            observer.info("repo %s has manifests disabled", self.repo.repo_id)
            return
        required_chksums = manifest_config.hashes
        distdir = domain.fetcher.distdir
        ret = []

        for key_query in sorted(set(match.unversioned_atom for match in matches)):
            pkgs = self.repo.match(key_query)
            if not pkgs:
                continue

            manifest = pkgs[0].manifest

            # all pkgdir fetchables
            pkgdir_fetchables = {}
            try:
                for pkg in pkgs:
                    pkgdir_fetchables.update({
                        fetchable.filename: fetchable for fetchable in
                        iflatten_instance(pkg._get_attr['fetchables'](
                            pkg, allow_missing_checksums=True,
                            skip_default_mirrors=(not mirrors)),
                            fetch.fetchable)
                        })
            except pkg_errors.MetadataException as e:
                observer.error("failed sourcing %s", pkg.cpvstr)
                ret.append(key_query)
                continue

            # fetchables targeted for manifest generation
            fetchables = {filename: fetchable for filename, fetchable in pkgdir_fetchables.iteritems()
                          if force or filename not in manifest.distfiles}

            # Manifest file is current and not forcing a refresh
            manifest_current = set(manifest.distfiles.iterkeys()) == set(pkgdir_fetchables.iterkeys())
            if manifest_config.thin and not fetchables and manifest_current:
                # Manifest files aren't necessary with thin manifests and no distfiles
                if os.path.exists(manifest.path) and not pkgdir_fetchables:
                    try:
                        os.remove(manifest.path)
                    except:
                        observer.error(
                            "failed removing old manifest: %s::%s",
                            key_query, self.repo.repo_id)
                        ret.append(key_query)
                continue

            pkg_ops = domain.pkg_operations(pkgs[0], observer=observer)
            if not pkg_ops.supports("fetch"):
                observer.error("pkg %s doesn't support fetching, can't generate manifest", pkg)
                ret.append(key_query)
                continue

            # fetch distfiles
            if not pkg_ops.fetch(list(fetchables.itervalues()), observer):
                ret.append(key_query)
                continue

            # calculate checksums for fetched distfiles
            for fetchable in fetchables.itervalues():
                d = dict(zip(
                    required_chksums,
                    get_chksums(pjoin(distdir, fetchable.filename), *required_chksums)))
                fetchable.chksums = d

            fetchables.update(pkgdir_fetchables)
            observer.info("generating manifest: %s::%s", key_query, self.repo.repo_id)
            manifest.update(sorted(fetchables.itervalues()), chfs=required_chksums)

        return ret


def _sort_eclasses(config, repo_config, eclasses):
    if eclasses:
        return eclasses

    repo_path = repo_config.location
    masters = repo_config.masters
    eclasses = []
    default = config.get_default('repo_config')
    if default is None:
        location = repo_path
    else:
        location = default.location

    if not masters:
        if masters is None:
            # if it's None, that means it's not a standalone, and is PMS, or misconfigured.
            # empty tuple means it's a standalone repository
            if default is None:
                raise Exception(
                    "repository %r named %r wants the default repository "
                    "(gentoo for example), but no repository is marked as the default. "
                    "Fix your configuration." % (repo_path, repo_config.repo_id))
            eclasses = [location]
    else:
        repo_map = {r.repo_id: r.location for r in
                    config.objects['repo_config'].itervalues()}

        missing = set(repo_config.masters).difference(repo_map)
        if missing:
            missing = ', '.join(sorted(missing))
            raise Exception(
                "repo %r at path %r has masters %s; we cannot find "
                "the following repos: %s"
                % (repo_config.repo_id, repo_path, ', '.join(map(repr, masters)), missing))
        eclasses = [repo_map[x] for x in masters]

    # add the repo's eclass directories if it's not specified.
    # do it in this fashion so that the repo's masters can actually interpose
    # this repo's eclasses in between others.
    # admittedly an odd thing to do, but it has some benefits
    if repo_path not in eclasses:
        eclasses.append(repo_path)

    eclasses = [eclass_cache_module.cache(pjoin(x, 'eclass'), location=location)
                for x in eclasses]

    if len(eclasses) == 1:
        eclasses = eclasses[0]
    else:
        eclasses = list(reversed(eclasses))
        eclasses = eclass_cache_module.StackedCaches(
            eclasses, location=location, eclassdir=location)
    return eclasses


@configurable(
    typename='repo',
    types={
        'repo_config': 'ref:repo_config', 'cache': 'refs:cache',
        'eclass_override': 'ref:eclass_cache',
        'default_mirrors': 'list',
        'ignore_paludis_versioning': 'bool',
        'allow_missing_manifests': 'bool'},
    requires_config='config')
def tree(config, repo_config, cache=(), eclass_override=None, default_mirrors=None,
         ignore_paludis_versioning=False, allow_missing_manifests=False):
    eclass_override = _sort_eclasses(config, repo_config, eclass_override)

    try:
        masters = tuple(config.objects['repo'][r] for r in repo_config.masters)
    except RuntimeError as e:
        # TODO: migrate to RecursionError when going >=py3.5
        if e.message.startswith('maximum recursion depth exceeded'):
            raise_from(errors.InitializationError(
                "'%s' repo has cyclic masters: %s" % (
                    repo_config.repo_id, ', '.join(repo_config.masters))))
        raise

    return _UnconfiguredTree(
        repo_config.location, eclass_override, masters=masters, cache=cache,
        default_mirrors=default_mirrors,
        ignore_paludis_versioning=ignore_paludis_versioning,
        allow_missing_manifests=allow_missing_manifests,
        repo_config=repo_config)


metadata_offset = "profiles"


class _UnconfiguredTree(prototype.tree):
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
        'ignore_paludis_versioning': 'bool',
        'allow_missing_manifests': 'bool',
        'repo_config': 'ref:repo_config',
        },
        typename='repo')

    def __init__(self, location, eclass_cache=None, masters=(), cache=(),
                 default_mirrors=None, ignore_paludis_versioning=False,
                 allow_missing_manifests=False, repo_config=None):

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
        :param ignore_paludis_versioning: If False, fail when -scm is encountered.  if True,
            silently ignore -scm ebuilds.
        """

        prototype.tree.__init__(self)
        self.base = self.location = location
        try:
            if not stat.S_ISDIR(os.stat(self.base).st_mode):
                raise errors.InitializationError(
                    "base not a dir: %s" % self.base)
        except OSError:
            raise_from(errors.InitializationError(
                "lstat failed on base %s" % (self.base,)))
        if repo_config is None:
            repo_config = repo_objs.RepoConfig(location)
        self.config = repo_config
        if eclass_cache is None:
            eclass_cache = eclass_cache_module.cache(pjoin(self.location, 'eclass'))
        self.eclass_cache = eclass_cache

        self.masters = masters
        self.trees = tuple(masters) + (self,)
        self.licenses = repo_objs.Licenses(self.location)
        if masters:
            self.licenses = repo_objs.OverlayedLicenses(*self.trees)

        mirrors = {}
        fp = pjoin(self.location, metadata_offset, "thirdpartymirrors")
        try:
            for k, v in read_dict(fp, splitter=None).iteritems():
                v = v.split()
                shuffle(v)
                mirrors[k] = v
        except EnvironmentError as ee:
            if ee.errno != errno.ENOENT:
                raise

        # use mirrors from masters if not defined in the repo
        for master in masters:
            for k, v in master.mirrors.iteritems():
                if k not in mirrors:
                    mirrors[k] = v

        if isinstance(cache, (tuple, list)):
            cache = tuple(cache)
        else:
            cache = (cache,)

        self.mirrors = mirrors
        self.default_mirrors = default_mirrors
        self.cache = cache
        self.ignore_paludis_versioning = ignore_paludis_versioning
        self._allow_missing_chksums = allow_missing_manifests
        self.package_class = self.package_factory(
            self, cache, self.eclass_cache, self.mirrors, self.default_mirrors)
        self._shared_pkg_cache = WeakValCache()

    repo_id = klass.alias_attr("config.repo_id")
    repo_name = klass.alias_attr("config.repo_name")

    def path_restrict(self, path):
        """Return a restriction from a given path in a repo.

        :param path: full or partial path to an ebuild
        :return: a package restriction matching the given path if possible
        :raises ValueError: if the repo doesn't contain the given path, the
            path relates to a file that isn't an ebuild, or the ebuild isn't in the
            proper directory layout
        """
        realpath = os.path.realpath(path)

        if realpath not in self:
            raise ValueError("'%s' repo doesn't contain: '%s'" % (self.repo_id, path))

        relpath = realpath[len(os.path.realpath(self.location)):].strip('/')
        repo_path = relpath.split(os.path.sep) if relpath else []
        restrictions = []

        if os.path.isfile(realpath):
            if not path.endswith('.ebuild'):
                raise ValueError("file is not an ebuild: '%s'" % (path,))
            elif len(repo_path) != 3:
                # ebuild isn't in a category/PN directory
                raise ValueError("ebuild not in the correct directory layout: '%s'" % (path,))

        # add restrictions until path components run out
        try:
            restrictions.append(restricts.RepositoryDep(self.repo_id))
            if repo_path[0] in self.categories:
                restrictions.append(restricts.CategoryDep(repo_path[0]))
                restrictions.append(restricts.PackageDep(repo_path[1]))
                base = cpv.versioned_CPV("%s/%s" % (repo_path[0], os.path.splitext(repo_path[2])[0]))
                restrictions.append(restricts.VersionMatch('=', base.version, rev=base.revision))
        except IndexError:
            pass
        return packages.AndRestriction(*restrictions)

    def __getitem__(self, cpv):
        cpv_inst = self.package_class(*cpv)
        if cpv_inst.fullver not in self.versions[(cpv_inst.category, cpv_inst.package)]:
            if cpv_inst.revision is None:
                if '%s-r0' % cpv_inst.fullver in \
                        self.versions[(cpv_inst.category, cpv_inst.package)]:
                    # ebuild on disk has an explicit -r0 in its name
                    return cpv_inst
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
    def hardcoded_categories(self):
        # try reading $LOC/profiles/categories if it's available.
        categories = readlines(
            pjoin(self.base, 'profiles', 'categories'),
            True, True, True)
        if categories is not None:
            categories = tuple(imap(intern, categories))
        return categories

    def _get_categories(self, *optional_category):
        # why the auto return? current porttrees don't allow/support
        # categories deeper then one dir.
        if optional_category:
            # raise KeyError
            return ()
        categories = set()
        for repo in self.trees:
            if repo.hardcoded_categories is not None:
                categories.update(repo.hardcoded_categories)
        if categories:
            return tuple(categories)
        try:
            return tuple(imap(intern, ifilterfalse(
                self.false_categories.__contains__,
                (x for x in listdir_dirs(self.base) if x[0:1] != "."))))
        except EnvironmentError as e:
            raise_from(KeyError("failed fetching categories: %s" % str(e)))

    def _get_packages(self, category):
        cpath = pjoin(self.base, category.lstrip(os.path.sep))
        try:
            return tuple(ifilterfalse(
                self.false_packages.__contains__, listdir_dirs(cpath)))
        except EnvironmentError as e:
            if e.errno == errno.ENOENT:
                if category in self.categories:
                    # ignore it, since it's PMS mandated that it be allowed.
                    return ()
            raise_from(KeyError(
                "failed fetching packages for category %s: %s" %
                (pjoin(self.base, category.lstrip(os.path.sep)), str(e))))

    def _get_versions(self, catpkg):
        cppath = pjoin(self.base, catpkg[0], catpkg[1])
        pkg = catpkg[-1] + "-"
        lp = len(pkg)
        extension = self.extension
        ext_len = -len(extension)
        try:
            ret = tuple(x[lp:ext_len] for x in listdir_files(cppath)
                        if x[ext_len:] == extension and x[:lp] == pkg)
            if any(('scm' in x or '-try' in x) for x in ret):
                if not self.ignore_paludis_versioning:
                    for x in ret:
                        if 'scm' in x:
                            raise ebuild_errors.InvalidCPV(
                                "%s/%s-%s has nonstandard -scm "
                                "version component" % (catpkg + (x,)))
                        elif 'try' in x:
                            raise ebuild_errors.InvalidCPV(
                                "%s/%s-%s has nonstandard -try "
                                "version component" % (catpkg + (x,)))
                    raise AssertionError('unreachable codepoint was reached')
                return tuple(x for x in ret
                             if ('scm' not in x and 'try' not in x))
            return ret
        except EnvironmentError as e:
            raise_from(KeyError(
                "failed fetching versions for package %s: %s" %
                (pjoin(self.base, '/'.join(catpkg)), str(e))))

    def _get_ebuild_path(self, pkg):
        if pkg.revision is None:
            if pkg.fullver not in self.versions[(pkg.category, pkg.package)]:
                # daft explicit -r0 on disk.
                return pjoin(
                    self.base, pkg.category, pkg.package,
                    "%s-%s-r0%s" % (pkg.package, pkg.fullver, self.extension))
        return pjoin(
            self.base, pkg.category, pkg.package,
            "%s-%s%s" % (pkg.package, pkg.fullver, self.extension))

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
            raise

    def __repr__(self):
        return "<ebuild %s location=%r @%#8x>" % (
            self.__class__.__name__, self.base, id(self))

    def _visibility_limiters(self):
        path = pjoin(self.base, 'profiles', 'package.mask')
        pos, neg = [], []
        try:
            if self.config.profile_formats.intersection(['portage-1', 'portage-2']):
                paths = sorted_scan(path)
            else:
                paths = [path]
            for path in paths:
                for line in iter_read_bash(path):
                    line = line.strip()
                    if line in ('-', ''):
                        raise profiles.ProfileError(
                            pjoin(self.base, 'profiles'),
                            'package.mask', "encountered empty negation: -")
                    if line.startswith('-'):
                        neg.append(atom.atom(line[1:]))
                    else:
                        pos.append(atom.atom(line))
        except IOError as i:
            if i.errno != errno.ENOENT:
                raise
        except ebuild_errors.MalformedAtom as ma:
            raise_from(profiles.ProfileError(
                pjoin(self.base, 'profiles'),
                'package.mask', ma))
        return [neg, pos]

    def _regen_operation_helper(self, **kwds):
        return _RegenOpHelper(
            self, force=bool(kwds.get('force', False)),
            eclass_caching=bool(kwds.get('eclass_caching', True)))


class _RegenOpHelper(object):

    def __init__(self, repo, force=False, eclass_caching=True):
        self.force = force
        self.eclass_caching = eclass_caching
        self.ebp = processor.request_ebuild_processor()
        if eclass_caching:
            self.ebp.allow_eclass_caching()

    def __call__(self, pkg):
        return pkg._fetch_metadata(ebp=self.ebp, force_regen=self.force)

    def finish(self):
        if self.eclass_caching:
            self.ebp.disable_eclass_caching()
        processor.release_ebuild_processor(self.ebp)
        self.ebp = None


class _ConfiguredTree(configured.tree):
    """Wrapper around a :obj:`_UnconfiguredTree` binding build/configuration data (USE)."""

    configurable = "use"
    config_wrappables = {
        x: klass.alias_method("evaluate_depset")
        for x in ("depends", "rdepends", "post_rdepends", "fetchables",
                  "license", "src_uri", "restrict", "required_use")}

    def __init__(self, raw_repo, domain, domain_settings, fetcher=None):
        """
        :param raw_repo: :obj:`_UnconfiguredTree` instance
        :param domain_settings: environment settings to bind
        :param fetcher: :obj:`pkgcore.fetch.base.fetcher` instance to use
            for getting access to fetchable files
        """

        if "USE" not in domain_settings:
            raise errors.InitializationError(
                "%s requires the following settings: 'USE', not supplied" % (
                    self.__class__,))

        elif 'CHOST' not in domain_settings:
            raise errors.InitializationError(
                "%s requires the following settings: 'CHOST', not supplied" % (
                    self.__class__,))

        chost = domain_settings['CHOST']
        scope_update = {'chost': chost}
        scope_update.update(
            (x, domain_settings.get(x.upper(), chost))
            for x in ('cbuild', 'ctarget'))
        scope_update.update(
            (x, domain_settings[x.upper()])
            for x in ('cflags', 'cxxflags', 'ldflags'))
        scope_update['operations_callback'] = self._generate_pkg_operations

        # update wrapped attr funcs requiring access to the class instance
        for k, v in self.config_wrappables.iteritems():
            if isinstance(v, basestring):
                self.config_wrappables[k] = getattr(self, v)

        configured.tree.__init__(
            self, raw_repo, self.config_wrappables,
            pkg_kls_injections=scope_update)

        self._get_pkg_use = domain.get_package_use_unconfigured
        self._get_pkg_use_for_building = domain.get_package_use_buildable
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
        profile_iuse_effective = self.domain.profile.iuse_effective
        return frozenset(profile_iuse_effective.union(raw_pkg_iuse_effective))

    @_wrap_attr(config_wrappables)
    def _distfiles(self, _raw_pkg_distfiles, enabled_use, pkg):
        return tuple(f.filename for f in pkg.fetchables.evaluate_depset(enabled_use))

    @_wrap_attr(config_wrappables)
    def _user_patches(self, _raw_pkg_patches, _enabled_use, pkg):
        # determine available user patches for >= EAPI 6
        if pkg.eapi.options.user_patches:
            patches = []
            patchroot = pjoin(self.domain.config_dir, 'patches')
            patch_dirs = [
                pkg.PF,
                '%s:%s' % (pkg.PF, pkg.slot),
                pkg.P,
                '%s:%s' % (pkg.P, pkg.slot),
                pkg.PN,
                '%s:%s' % (pkg.PN, pkg.slot),
            ]
            for d in patch_dirs:
                for root, _dirs, files in os.walk(pjoin(patchroot, pkg.category, d)):
                    patches.extend([pjoin(root, f) for f in sorted(files, key=locale.strxfrm)
                                    if f.endswith(('.diff', '.patch'))])
            return tuple(patches)
        return None

    def _get_delayed_immutable(self, pkg, immutable):
        return InvertedContains(set(pkg.iuse).difference(immutable))

    def _get_pkg_kwds(self, pkg):
        immutable, enabled, disabled = self._get_pkg_use(pkg)
        return {
            "initial_settings": enabled,
            "unchangable_settings": self._delayed_iuse(
                self._get_delayed_immutable, pkg, immutable)}

    def _generate_pkg_operations(self, domain, pkg, **kwds):
        fetcher = self._fetcher_override
        if fetcher is None:
            fetcher = domain.fetcher
        return ebd.src_operations(
            domain, pkg, pkg.repo.eclass_cache, fetcher=fetcher,
            use_override=self._get_pkg_use_for_building(pkg), **kwds)


_UnconfiguredTree.configure = _ConfiguredTree
