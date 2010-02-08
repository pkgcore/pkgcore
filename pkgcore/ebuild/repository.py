# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
ebuild repository, specific to gentoo ebuild trees (whether cvs or rsync)
"""

import os, stat
from itertools import imap, ifilterfalse

from pkgcore.repository import prototype, errors, configured, syncable
from pkgcore.ebuild import eclass_cache as eclass_cache_module
from pkgcore.config import ConfigHint
from pkgcore.plugin import get_plugin

from snakeoil.fileutils import read_dict, iter_read_bash
from snakeoil import currying
from snakeoil.osutils import listdir_files, readfile, listdir_dirs, pjoin
from snakeoil.containers import InvertedContains
from snakeoil.obj import make_kls
from snakeoil.weakrefs import WeakValCache
from snakeoil.compatibility import any, intern

from snakeoil.demandload import demandload
demandload(globals(),
    'pkgcore.ebuild.ebd:buildable',
    'pkgcore.interfaces.data_source:local_source',
    'pkgcore.ebuild:digest,repo_objs,atom',
    'pkgcore.ebuild:errors@ebuild_errors',
    'pkgcore.ebuild:profiles',
    'random:shuffle',
    'errno',
)


metadata_offset = "profiles"

class UnconfiguredTree(syncable.tree_mixin, prototype.tree):

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
    format_magic = "ebuild_src"
    enable_gpg = False
    extension = '.ebuild'

    pkgcore_config_type = ConfigHint(
        {'location': 'str', 'cache': 'refs:cache',
         'eclass_cache': 'ref:eclass_cache',
         'default_mirrors': 'list', 'sync': 'lazy_ref:syncer',
         'override_repo_id':'str',
         'ignore_paludis_versioning':'bool'},
        typename='repo')

    def __init__(self, location, cache=(), eclass_cache=None,
                 default_mirrors=None, sync=None, override_repo_id=None,
                 ignore_paludis_versioning=False):

        """
        @param location: on disk location of the tree
        @param cache: sequence of L{pkgcore.cache.template.database} instances
            to use for storing metadata
        @param eclass_cache: If not None, L{pkgcore.ebuild.eclass_cache}
            instance representing the eclasses available,
            if None, generates the eclass_cache itself
        @param default_mirrors: Either None, or sequence of mirrors to try
            fetching from first, then falling back to other uri
        @param override_repo_id: Either None, or string to force as the
            repository unique id
        @param sync: Either None, or a syncer object to use for updating of this
            repository.
        @param ignore_paludis_versioning: If False, fail when -scm is encountred.  if True,
            silently ignore -scm ebuilds.
        """

        prototype.tree.__init__(self)
        syncable.tree_mixin.__init__(self, sync)
        self._repo_id = override_repo_id
        self.base = self.location = location
        try:
            if not stat.S_ISDIR(os.stat(self.base).st_mode):
                raise errors.InitializationError(
                    "base not a dir: %s" % self.base)

        except OSError:
            raise errors.InitializationError(
                "lstat failed on base %s" % self.base)
        if eclass_cache is None:
            self.eclass_cache = eclass_cache_module.cache(
                pjoin(self.base, "eclass"), self.base)
        else:
            self.eclass_cache = eclass_cache

        self.licenses = repo_objs.Licenses(location)

        fp = pjoin(self.base, metadata_offset, "thirdpartymirrors")
        mirrors = {}
        if os.path.exists(fp):
            f = open(fp, "r")
            try:
                for k, v in read_dict(f, splitter=None,
                                      source_isiter=True).iteritems():
                    v = v.split()
                    shuffle(v)
                    mirrors[k] = v
            finally:
                f.close()
        if isinstance(cache, (tuple, list)):
            cache = tuple(cache)
        else:
            cache = (cache,)

        self.mirrors = mirrors
        self.default_mirrors = default_mirrors
        self.cache = cache
        self.ignore_paludis_versioning = ignore_paludis_versioning
        self.package_class = get_plugin("format." + self.format_magic)(
            self, cache, self.eclass_cache, self.mirrors, self.default_mirrors)
        self._shared_pkg_cache = WeakValCache()

    @property
    def repo_id(self):
        if self._repo_id is None:
            # thank you spb for a stupid location, and stupid file name.
            r = readfile(pjoin(self.location, "profiles",
                "repo_name"), True)
            if r is None:
                self._repo_id = self.location
            else:
                self._repo_id = r.strip()
        return self._repo_id

    def __getitem__(self, cpv):
        cpv_inst = self.package_class(*cpv)
        if cpv_inst.fullver not in self.versions[(cpv_inst.category, cpv_inst.package)]:
            if cpv_inst.revision is None:
                if '%s-r0' % cpv_inst.fullver in \
                    self.versions[(cpv_inst.category, cpv_inst.package)]:
                    # ebuild on disk has an explicit -r0 in it's name
                    return cpv_inst
            del cpv_inst
            raise KeyError(cpv)
        return cpv_inst


    def rebind(self, **kwds):

        """
        generate a new tree instance with the same location using new keywords.

        @param kwds: see __init__ for valid values
        """

        o = self.__class__(self.location, **kwds)
        o.categories = self.categories
        o.packages = self.packages
        o.versions = self.versions
        return o

    def _get_categories(self, *optional_category):
        # why the auto return? current porttrees don't allow/support
        # categories deeper then one dir.
        if optional_category:
            #raise KeyError
            return ()

        try:
            # try reading $LOC/profiles/categories if it's available.
            try:
                cats = iter_read_bash(pjoin(self.base, 'profiles',
                    'categories'))
                return tuple(imap(intern, cats))
            except IOError, e:
                if e.errno != errno.ENOENT:
                    raise

            return tuple(imap(intern,
                ifilterfalse(self.false_categories.__contains__,
                    (x for x in listdir_dirs(self.base) if x[0:1] != ".")
                )))
        except (OSError, IOError), e:
            raise KeyError("failed fetching categories: %s" % str(e))

    def _get_packages(self, category):
        cpath = pjoin(self.base, category.lstrip(os.path.sep))
        try:
            return tuple(ifilterfalse(self.false_packages.__contains__,
                listdir_dirs(cpath)))
        except (OSError, IOError), e:
            raise KeyError("failed fetching packages for category %s: %s" % \
                    (pjoin(self.base, category.lstrip(os.path.sep)), \
                    str(e)))

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
        except (OSError, IOError), e:
            raise KeyError("failed fetching versions for package %s: %s" % \
                (pjoin(self.base, catpkg.lstrip(os.path.sep)), str(e)))

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
        return repo_objs.Manifest(pjoin(self.base, category, package,
            "Manifest"), enforce_gpg=self.enable_gpg)

    def _get_digests(self, pkg, force_manifest1=False):
        manifest = pkg._shared_pkg_data.manifest
        if manifest.version == 2 and not force_manifest1:
            return manifest.distfiles
        return digest.parse_digest(pjoin(
            os.path.dirname(self._get_ebuild_path(pkg)), "files",
            "digest-%s-%s" % (pkg.package, pkg.fullver)))

    def __str__(self):
        return "%s.%s: location %s" % (
            self.__class__.__module__, self.__class__.__name__, self.base)

    def __repr__(self):
        return "<ebuild %s location=%r @%#8x>" % (self.__class__.__name__,
            self.base, id(self))

    def _visibility_limiters(self):
        path = pjoin(self.base, 'profiles', 'package.mask')
        try:
            return [atom.atom(x.strip())
                for x in iter_read_bash(path)]
        except IOError, i:
            if i.errno != errno.ENOENT:
                raise
            return []
        except ebuild_errors.MalformedAtom, ma:
            raise profiles.ProfileError(pjoin(self.base, 'profiles'),
                'package.mask', ma)


class SlavedTree(UnconfiguredTree):

    """
    repository that pulls repo metadata from a parent repo; mirrors
    being the main metadata pulled at this point
    """

    orig_hint = UnconfiguredTree.pkgcore_config_type
    d = dict(orig_hint.types.iteritems())
    d["parent_repo"] = 'ref:repo'
    pkgcore_config_type = orig_hint.clone(types=d,
        required=list(orig_hint.required) + ["parent_repo"],
        positional=list(orig_hint.positional) + ["parent_repo"])
    del d, orig_hint

    def __init__(self, parent_repo, *args, **kwds):
        UnconfiguredTree.__init__(self, *args, **kwds)
        for k, v in parent_repo.mirrors.iteritems():
            if k not in self.mirrors:
                self.mirrors[k] = v
        self.package_class = get_plugin("format." + self.format_magic)(
            self, self.cache, self.eclass_cache, self.mirrors,
            self.default_mirrors)


class ConfiguredTree(configured.tree):

    """
    wrapper around a L{UnconfiguredTree} binding build/configuration data (USE)
    """

    configurable = "use"
    config_wrappables = dict(
        (x, currying.alias_class_method("evaluate_depset"))
        for x in ["depends", "rdepends", "post_rdepends", "fetchables",
                  "license", "src_uri", "license", "provides"])

    def __init__(self, raw_repo, domain, domain_settings, fetcher=None):
        """
        @param raw_repo: L{UnconfiguredTree} instance
        @param domain_settings: environment settings to bind
        @param fetcher: L{pkgcore.fetch.base.fetcher} instance to use
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

        configured.tree.__init__(self, raw_repo, self.config_wrappables,
           pkg_kls_injections=scope_update)
        self._get_pkg_use = domain.get_package_use
        self.domain_settings = domain_settings
        if fetcher is None:
            self.fetcher = self.domain_settings["fetcher"]
        else:
            self.fetcher = fetcher
        self._delayed_iuse = currying.partial(make_kls(InvertedContains),
            InvertedContains)

    def _get_delayed_immutable(self, pkg, immutable):
        return InvertedContains(pkg.iuse.difference(immutable))

    def _get_pkg_kwds(self, pkg):
        immutable, enabled, disabled = self._get_pkg_use(pkg)
        return {
            "initial_settings": enabled,
            "unchangable_settings": self._delayed_iuse(
                self._get_delayed_immutable, pkg, immutable),
            "build_callback":self.generate_buildop}

    def generate_buildop(self, pkg, **kwds):
        return buildable(pkg, self.domain_settings, pkg.repo.eclass_cache,
                         self.fetcher, **kwds)

UnconfiguredTree.configure = ConfiguredTree
tree = UnconfiguredTree
