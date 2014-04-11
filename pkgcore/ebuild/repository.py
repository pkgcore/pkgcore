# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
ebuild repository, specific to gentoo ebuild trees (whether cvs or rsync)
"""

__all__ = ("tree", "slavedtree",)

import os, stat
from itertools import imap, ifilterfalse

from pkgcore.repository import prototype, errors, configured
from pkgcore.ebuild import eclass_cache as eclass_cache_module
from pkgcore.ebuild import ebuild_src
from pkgcore.config import ConfigHint, configurable
from pkgcore.plugin import get_plugin
from pkgcore.operations import repo as _repo_ops

from snakeoil import klass
from snakeoil.fileutils import readlines
from snakeoil.bash import iter_read_bash, read_dict
from snakeoil.currying import partial
from snakeoil.osutils import listdir_files, listdir_dirs, pjoin
from snakeoil.fileutils import readfile
from snakeoil.containers import InvertedContains
from snakeoil.obj import make_kls
from snakeoil.weakrefs import WeakValCache
from snakeoil.compatibility import intern, raise_from

from snakeoil.demandload import demandload
demandload(globals(),
    'pkgcore.ebuild:ebd',
    'snakeoil.data_source:local_source',
    'snakeoil.chksum:get_chksums',
    'pkgcore.ebuild:digest,repo_objs,atom',
    'pkgcore.ebuild:errors@ebuild_errors',
    'pkgcore.ebuild:profiles,processor',
    'pkgcore.package:errors@pkg_errors',
    'pkgcore.util.packages:groupby_pkg',
    'pkgcore.fs.livefs:iter_scan',
    'pkgcore.log:logger',
    'operator:attrgetter',
    'random:shuffle',
    'errno',
)


class repo_operations(_repo_ops.operations):

    def _cmd_implementation_digests(self, domain, matches, observer, **options):
        manifest_config = self.repo.config.manifests
        if manifest_config.disabled:
            observer.info("repo %s has manifests diabled" % (self.repo,))
            return
        required = manifest_config.hashes
        ret = False
        for key_query in sorted(set(match.unversioned_atom for match in matches)):
            observer.info("generating digests for %s for repo %s", key_query, self.repo)
            packages = self.repo.match(key_query, sorter=sorted)
            if packages:
                observer.info("generating digests for %s for repo %s", key_query, self.repo)
            pkgdir_fetchables = {}
            try:
                for pkg in packages:
                    # XXX: needs modification to grab all sources, and also to not
                    # bail if digests are missing
                    pkg.release_cached_data(all=True)
                    # heinous.
                    fetchables = pkg._get_attr['fetchables'](pkg, allow_missing_checksums=True)
                    object.__setattr__(pkg, 'fetchables', fetchables)
                    pkg_ops = domain.pkg_operations(pkg, observer=observer)
                    if not pkg_ops.supports("fetch"):
                        observer.error("pkg %s doesn't support fetching, can't generate manifest/digest info\n",
                            pkg)
                    if not pkg_ops.mirror(observer):
                        observer.error("failed fetching for pkg %s" % (pkg,))
                        return False

                    fetchables = pkg_ops._mirror_op.verified_files
                    for path, fetchable in fetchables.iteritems():
                        d = dict(zip(required, get_chksums(path, *required)))
                        fetchable.chksums = d
                    # should report on conflicts here...
                    pkgdir_fetchables.update(fetchables.iteritems())

                pkgdir_fetchables = sorted(pkgdir_fetchables.itervalues())
                digest.serialize_manifest(os.path.dirname(pkg.ebuild.get_path()),
                    pkgdir_fetchables, chfs=required, thin=manifest_config.thin)
                ret = True
            finally:
                for pkg in packages:
                    # done since we do hackish shit above
                    # should be uneeded once this is cleaned up
                    pkg.release_cached_data(all=True)
        return ret

def _sort_eclasses(config, raw_repo, eclasses):
    if eclasses:
        return eclasses

    loc = raw_repo.location
    masters = raw_repo.masters
    eclasses = []
    default = portdir = config.get_default('raw_repo')
    if portdir is None:
        portdir = loc
    else:
        portdir = portdir.location

    if not masters:
        if masters is None and raw_repo.repo_id != 'gentoo':
            # if it's None, that means it's not a standalone, and is PMS, or misconfigured.
            # empty tuple means it's a standalone repository
            if default is None:
                raise Exception("repository %r named %r wants the default repository "
                    "(portdir for example), but no repository is marked as the default. "
                    "Fix your configuration." % (loc, raw_repo.repo_id))
            eclasses = [default.location]
    else:
        repo_map = dict((r.repo_id, r.location) for r in
            config.objects['raw_repo'].itervalues())

        missing = set(raw_repo.masters).difference(repo_map)
        if missing:
            missing = ', '.join(sorted(missing))
            raise Exception("repo %r at path %r has masters %s; we cannot find "
                "the following repositories: %s"
                    % (raw_repo.repo_id, loc, ', '.join(map(repr, masters)), missing))
        eclasses = [repo_map[x] for x in masters]

    # add the repositories eclasses directories if it's not specified.
    # do it in this fashion so that the repositories masters can actually interpose
    # this repositories eclasses in between others.
    # admittedly an odd thing to do, but it has some benefits
    if loc not in eclasses:
        eclasses.append(loc)

    eclasses = [eclass_cache_module.cache(pjoin(x, 'eclass'), portdir=portdir)
        for x in eclasses]

    if len(eclasses) == 1:
        eclasses = eclasses[0]
    else:
        eclasses = list(reversed(eclasses))
        eclasses = eclass_cache_module.StackedCaches(eclasses, portdir=portdir,
            eclassdir=portdir)
    return eclasses


@configurable(typename='repo',
        types={'raw_repo': 'ref:raw_repo', 'cache': 'refs:cache',
         'eclass_override': 'ref:eclass_cache',
         'default_mirrors': 'list',
         'override_repo_id':'str',
         'ignore_paludis_versioning':'bool',
         'allow_missing_manifests':'bool'},
         requires_config='config')
def tree(config, raw_repo, cache=(), eclass_override=None, default_mirrors=None,
         ignore_paludis_versioning=False, allow_missing_manifests=False):
    eclass_override = _sort_eclasses(config, raw_repo, eclass_override)

    return _UnconfiguredTree(raw_repo.location, eclass_override, cache=cache,
        default_mirrors=default_mirrors,
        ignore_paludis_versioning=ignore_paludis_versioning,
        allow_missing_manifests=allow_missing_manifests,
        repo_config=raw_repo)

@configurable(typename='repo',
        types={'raw_repo': 'ref:raw_repo', 'cache': 'refs:cache',
         'parent_repo':'ref:repo',
         'eclass_override': 'ref:eclass_cache',
         'default_mirrors': 'list',
         'override_repo_id':'str',
         'ignore_paludis_versioning':'bool',
         'allow_missing_manifests':'bool'},
         requires_config='config')
def slavedtree(config, raw_repo, parent_repo, cache=(), eclass_override=None, default_mirrors=None,
               ignore_paludis_versioning=False, allow_missing_manifests=False):
    eclass_override = _sort_eclasses(config, raw_repo, eclass_override)

    return _SlavedTree(parent_repo, raw_repo.location, eclass_override, cache=cache,
        default_mirrors=default_mirrors,
        ignore_paludis_versioning=ignore_paludis_versioning,
        allow_missing_manifests=allow_missing_manifests,
        repo_config=raw_repo)


metadata_offset = "profiles"

class _UnconfiguredTree(prototype.tree):

    """
    raw implementation supporting standard ebuild tree.

    return packages don't have USE configuration bound to them.
    """

    false_packages = frozenset(["CVS", ".svn"])
    false_categories = frozenset([
            "eclass", "profiles", "packages", "distfiles", "metadata",
            "licenses", "scripts", "CVS", "local"])
    configured = False
    configurables = ("domain", "settings")
    configure = None
    package_factory = staticmethod(ebuild_src.generate_new_factory)
    # This attributes needs to be replaced/removed; it's a hack for pmerge.
    repository_type = 'source'
    enable_gpg = False
    extension = '.ebuild'

    operations_kls = repo_operations

    pkgcore_config_type = ConfigHint(
        {'location': 'str', 'cache': 'refs:cache',
         'eclass_cache': 'ref:eclass_cache',
         'default_mirrors': 'list',
         'override_repo_id':'str',
         'ignore_paludis_versioning':'bool',
         'allow_missing_manifests':'bool',
         'repo_config':'ref:raw_repo',
        },
        typename='repo')

    def __init__(self, location, eclass_cache, cache=(),
                 default_mirrors=None, override_repo_id=None,
                 ignore_paludis_versioning=False, allow_missing_manifests=False,
                 repo_config=None):

        """
        :param location: on disk location of the tree
        :param cache: sequence of :obj:`pkgcore.cache.template.database` instances
            to use for storing metadata
        :param eclass_cache: If not None, :obj:`pkgcore.ebuild.eclass_cache`
            instance representing the eclasses available,
            if None, generates the eclass_cache itself
        :param default_mirrors: Either None, or sequence of mirrors to try
            fetching from first, then falling back to other uri
        :param override_repo_id: Either None, or string to force as the
            repository unique id
        :param ignore_paludis_versioning: If False, fail when -scm is encountred.  if True,
            silently ignore -scm ebuilds.
        """

        prototype.tree.__init__(self)
        if repo_config is None:
            repo_config = repo_objs.RepoConfig(location)
        self.config = repo_config
        self._repo_id = override_repo_id
        self.base = self.location = location
        try:
            if not stat.S_ISDIR(os.stat(self.base).st_mode):
                raise errors.InitializationError(
                    "base not a dir: %s" % self.base)

        except OSError:
            raise_from(errors.InitializationError(
                "lstat failed on base %s" % (self.base,)))
        self.eclass_cache = eclass_cache

        self.licenses = repo_objs.Licenses(location)

        fp = pjoin(self.base, metadata_offset, "thirdpartymirrors")
        mirrors = {}
        try:
            for k, v in read_dict(fp, splitter=None).iteritems():
                v = v.split()
                shuffle(v)
                mirrors[k] = v
        except EnvironmentError, ee:
            if ee.errno != errno.ENOENT:
                raise

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

    def __getitem__(self, cpv):
        cpv_inst = self.package_class(*cpv)
        if cpv_inst.fullver not in self.versions[(cpv_inst.category, cpv_inst.package)]:
            if cpv_inst.revision is None:
                if '%s-r0' % cpv_inst.fullver in \
                    self.versions[(cpv_inst.category, cpv_inst.package)]:
                    # ebuild on disk has an explicit -r0 in it's name
                    return cpv_inst
            raise KeyError(cpv)
        return cpv_inst

    def rebind(self, **kwds):

        """
        generate a new tree instance with the same location using new keywords.

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
        cats = readlines(pjoin(self.base, 'profiles', 'categories'),
            True, True, True)
        if cats is not None:
            cats = tuple(imap(intern, cats))
        return cats

    def _get_categories(self, *optional_category):
        # why the auto return? current porttrees don't allow/support
        # categories deeper then one dir.
        if optional_category:
            #raise KeyError
            return ()
        cats = self.hardcoded_categories
        if cats is not None:
            return cats
        try:
            return tuple(imap(intern,
                ifilterfalse(self.false_categories.__contains__,
                    (x for x in listdir_dirs(self.base) if x[0:1] != ".")
                )))
        except EnvironmentError, e:
            raise_from(KeyError("failed fetching categories: %s" % str(e)))

    def _get_packages(self, category):
        cpath = pjoin(self.base, category.lstrip(os.path.sep))
        try:
            return tuple(ifilterfalse(self.false_packages.__contains__,
                listdir_dirs(cpath)))
        except EnvironmentError, e:
            if e.errno == errno.ENOENT:
                if self.hardcoded_categories and category in self.hardcoded_categories:
                    # ignore it, since it's PMS mandated that it be allowed.
                    return ()
            raise_from(KeyError("failed fetching packages for category %s: %s" % \
                (pjoin(self.base, category.lstrip(os.path.sep)), \
                str(e))))

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
                            raise ebuild_errors.InvalidCPV("%s/%s-%s has nonstandard -scm "
                                "version component" % (catpkg + (x,)))
                        elif 'try' in x:
                            raise ebuild_errors.InvalidCPV("%s/%s-%s has nonstandard -try "
                                "version component" % (catpkg + (x,)))
                    raise AssertionError('unreachable codepoint was reached')
                return tuple(x for x in ret
                    if ('scm' not in x and 'try' not in x))
            return ret
        except EnvironmentError, e:
            raise_from(KeyError("failed fetching versions for package %s: %s" % \
                (pjoin(self.base, catpkg.lstrip(os.path.sep)), str(e))))

    def _get_ebuild_path(self, pkg):
        if pkg.revision is None:
            if pkg.fullver not in self.versions[(pkg.category, pkg.package)]:
                # daft explicit -r0 on disk.
                return pjoin(self.base, pkg.category, pkg.package,
                    "%s-%s-r0%s" % (pkg.package, pkg.fullver, self.extension))
        return pjoin(self.base, pkg.category, pkg.package, \
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
        return repo_objs.LocalMetadataXml(pjoin(self.base, category,
            package, "metadata.xml"))

    def _get_manifest(self, category, package):
        return digest.Manifest(pjoin(self.base, category, package,
            "Manifest"), thin=self.config.manifests.thin,
                enforce_gpg=self.enable_gpg)

    def _get_digests(self, pkg, allow_missing=False):
        if self.config.manifests.disabled:
            return True, {}
        try:
            manifest = pkg._shared_pkg_data.manifest
            return allow_missing, manifest.distfiles
        except pkg_errors.ParseChksumError, e:
            if e.missing and allow_missing:
                return allow_missing, {}
            raise

    def __str__(self):
        return "%s.%s: location %s" % (
            self.__class__.__module__, self.__class__.__name__, self.base)

    def __repr__(self):
        return "<ebuild %s location=%r @%#8x>" % (self.__class__.__name__,
            self.base, id(self))

    def _visibility_limiters(self):
        path = pjoin(self.base, 'profiles', 'package.mask')
        pos, neg = [], []
        try:
            if self.config.profile_format not in ['pms', 'portage-2']:
                paths = sorted(x.location for x in iter_scan(path)
                    if x.is_reg)
            else:
                paths = [path]
            for path in paths:
                for line in iter_read_bash(path):
                    line = line.strip()
                    if line in ('-', ''):
                        raise profiles.ProfileError(pjoin(self.base, 'profiles'),
                            'package.mask', "encountered empty negation: -")
                    if line.startswith('-'):
                        neg.append(atom.atom(line[1:]))
                    else:
                        pos.append(atom.atom(line))
        except IOError, i:
            if i.errno != errno.ENOENT:
                raise
        except ebuild_errors.MalformedAtom, ma:
            raise_from(profiles.ProfileError(pjoin(self.base, 'profiles'),
                'package.mask', ma))
        return [neg, pos]

    def _regen_operation_helper(self, **kwds):
        return _RegenOpHelper(self, force=bool(kwds.get('force', False)),
            eclass_caching=bool(kwds.get('eclass_caching', True)))


class _RegenOpHelper(object):

    def __init__(self, repo, force=False, eclass_caching=True):
        self.force=force
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


class _SlavedTree(_UnconfiguredTree):

    """
    repository that pulls repo metadata from a parent repo; mirrors
    being the main metadata pulled at this point
    """

    orig_hint = _UnconfiguredTree.pkgcore_config_type
    d = dict(orig_hint.types.iteritems())
    d["parent_repo"] = 'ref:repo'
    pkgcore_config_type = orig_hint.clone(types=d,
        required=list(orig_hint.required) + ["parent_repo"],
        positional=list(orig_hint.positional) + ["parent_repo"])
    del d, orig_hint

    def __init__(self, parent_repo, *args, **kwds):
        _UnconfiguredTree.__init__(self, *args, **kwds)
        for k, v in parent_repo.mirrors.iteritems():
            if k not in self.mirrors:
                self.mirrors[k] = v
        self.package_class = self.package_factory(
            self, self.cache, self.eclass_cache, self.mirrors,
            self.default_mirrors)
        self.parent_repo = parent_repo

    def _get_categories(self, *optional_category):
        categories = super(_SlavedTree, self)._get_categories(optional_category)
        return tuple(set(categories + tuple(self.parent_repo.categories)))


class _ConfiguredTree(configured.tree):

    """
    wrapper around a :obj:`_UnconfiguredTree` binding build/configuration data (USE)
    """

    configurable = "use"
    config_wrappables = dict((x, klass.alias_method("evaluate_depset"))
        for x in ["depends", "rdepends", "post_rdepends", "fetchables",
                  "license", "src_uri", "provides", "restrict",
                  "required_use"])

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
        scope_update.update((x, domain_settings.get(x.upper(), chost))
            for x in ('cbuild', 'ctarget'))
        scope_update['operations_callback'] = self._generate_pkg_operations

        self.config_wrappables['iuse_effective'] = partial(
            self._generate_iuse_effective, domain.profile)
        configured.tree.__init__(self, raw_repo, self.config_wrappables,
            pkg_kls_injections=scope_update)
        self._get_pkg_use = domain.get_package_use_unconfigured
        self._get_pkg_use_for_building = domain.get_package_use_buildable
        self.domain_settings = domain_settings
        self.fetcher_override = fetcher
        self._delayed_iuse = partial(make_kls(InvertedContains),
            InvertedContains)

    def _generate_iuse_effective(self, profile, pkg, *args):
        iuse_effective = [x.lstrip('-+') for x in pkg.iuse]
        use_expand = frozenset(profile.use_expand)

        if pkg.eapi_obj.options.profile_iuse_injection:
            iuse_effective.extend(profile.iuse_implicit)
            use_expand_implicit = frozenset(profile.use_expand_implicit)
            use_expand_unprefixed = frozenset(profile.use_expand_unprefixed)

            for v in use_expand_implicit.intersection(use_expand_unprefixed):
                iuse_effective.extend(profile.default_env.get("USE_EXPAND_VALUES_" + v, "").split())
            for v in use_expand.intersection(use_expand_implicit):
                for x in profile.default_env.get("USE_EXPAND_VALUES_" + v, "").split():
                    iuse_effective.append(v.lower() + "_" + x)
        else:
            iuse_effective.extend(pkg.repo.config.known_arches)
            iuse_effective.extend(x.lower() + "_.*" for x in use_expand)

        return tuple(sorted(set(iuse_effective)))

    def _get_delayed_immutable(self, pkg, immutable):
        return InvertedContains(pkg.iuse.difference(immutable))

    def _get_pkg_kwds(self, pkg):
        immutable, enabled, disabled = self._get_pkg_use(pkg)
        return {
            "initial_settings": enabled,
            "unchangable_settings": self._delayed_iuse(
                self._get_delayed_immutable, pkg, immutable)}

    def _generate_pkg_operations(self, domain, pkg, **kwds):
        fetcher = self.fetcher_override
        if fetcher is None:
            fetcher = domain.fetcher
        return ebd.src_operations(domain, pkg, pkg.repo.eclass_cache, fetcher=fetcher,
            use_override=self._get_pkg_use_for_building(pkg), **kwds)


_UnconfiguredTree.configure = _ConfiguredTree

# XXX compatibility hacks for pcheck
SlavedTree = _SlavedTree
UnconfiguredTree = _UnconfiguredTree
