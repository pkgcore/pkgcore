# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
ebuild repository, specific to gentoo ebuild trees (whether cvs or rsync)
"""

import os, stat
from pkgcore.repository import prototype, errors, configured, syncable
from pkgcore.util.file import read_dict, iter_read_bash
from pkgcore.util import currying
from pkgcore.util.osutils import (listdir_files, readfile, listdir_dirs,
    join as pjoin)
from pkgcore.ebuild import eclass_cache as eclass_cache_module
from pkgcore.util.demandload import demandload
from pkgcore.util.containers import InvertedContains
from pkgcore.util.obj import make_kls
from pkgcore.util.weakrefs import WeakValCache
demandload(globals(), "pkgcore.ebuild.ebd:buildable "
    "pkgcore.interfaces.data_source:local_source "
    "pkgcore.ebuild:digest "
    "pkgcore.ebuild:repo_objs "
    "pkgcore.ebuild:atom "
    "errno ")

from pkgcore.config import ConfigHint
from pkgcore.plugin import get_plugin

metadata_offset = "profiles"

class UnconfiguredTree(syncable.tree_mixin, prototype.tree):

    """
    raw implementation supporting standard ebuild tree.

    return packages don't have USE configuration bound to them.
    """

    false_packages = frozenset(["CVS", ".svn"])
    false_categories = frozenset([
            "eclass", "profiles", "packages", "distfiles", "metadata",
            "licenses", "scripts", "CVS", ".svn"])
    configured = False
    configurables = ("domain", "settings",)
    configure = None
    format_magic = "ebuild_src"
    enable_gpg = False

    pkgcore_config_type = ConfigHint(
        {'location': 'str', 'cache': 'refs:cache',
         'eclass_cache': 'ref:eclass_cache', 'mirrors_file': 'str',
         'default_mirrors': 'list', 'sync': 'lazy_ref:syncer',
         'override_repo_id':'str'},
        typename='repo')

    def __init__(self, location, cache=(), eclass_cache=None,
                 mirrors_file=None, default_mirrors=None, sync=None,
                 override_repo_id=None):

        """
        @param location: on disk location of the tree
        @param cache: sequence of L{pkgcore.cache.template.database} instances
            to use for storing metadata
        @param eclass_cache: If not None, L{pkgcore.ebuild.eclass_cache}
            instance representing the eclasses available,
            if None, generates the eclass_cache itself
        @param mirrors_file: file parsed via L{read_dict} to get mirror tiers
        @param default_mirrors: Either None, or sequence of mirrors to try
            fetching from first, then falling back to other uri
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
        if mirrors_file:
            mirrors = read_dict(pjoin(self.base, metadata_offset,
                                             "thirdpartymirrors"))
        else:
            mirrors = {}
        fp = pjoin(self.base, metadata_offset, "thirdpartymirrors")
        if os.path.exists(fp):
            from random import shuffle
            f = None
            try:
                f = open(pjoin(self.base, metadata_offset,
                                      "thirdpartymirrors"), "r")
                for k, v in read_dict(f, splitter="\t",
                                      source_isiter=True).items():
                    v = v.split()
                    shuffle(v)
                    mirrors.setdefault(k, []).extend(v)
            except OSError:
                if f is not None:
                    f.close()
                raise

        if isinstance(cache, (tuple, list)):
            cache = tuple(cache)
        else:
            cache = (cache,)

        self.mirrors = mirrors
        self.default_mirrors = default_mirrors
        self.cache = cache
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
        if len(optional_category):
            #raise KeyError
            return ()

        try:
            return tuple(intern(x) for x in listdir_dirs(self.base)
                         if x not in self.false_categories)
        except (OSError, IOError), e:
            raise KeyError("failed fetching categories: %s" % str(e))

    def _get_packages(self, category):
        cpath = pjoin(self.base, category.lstrip(os.path.sep))
        try:
            return tuple(x for x in listdir_dirs(cpath) if x not in
                self.false_packages)

        except (OSError, IOError), e:
            raise KeyError("failed fetching packages for category %s: %s" % \
                    (pjoin(self.base, category.lstrip(os.path.sep)), \
                    str(e)))

    def _get_versions(self, catpkg):
        pkg = catpkg[-1]
        cppath = pjoin(self.base, catpkg[0], catpkg[1])
        # 7 == len(".ebuild")
        try:
            return tuple(x[len(pkg):-7].lstrip("-")
                         for x in listdir_files(cppath)
                if x.endswith(".ebuild") and x.startswith(pkg))
        except (OSError, IOError), e:
            raise KeyError("failed fetching versions for package %s: %s" % \
                (pjoin(self.base, catpkg.lstrip(os.path.sep)), str(e)))

    def _get_ebuild_path(self, pkg):
        return pjoin(self.base, pkg.category, pkg.package, \
            "%s-%s.ebuild" % (pkg.package, pkg.fullver))

    def _get_ebuild_src(self, pkg):
        return local_source(self._get_ebuild_path(pkg))

    def _get_shared_pkg_data(self, category, package):
        key = (category, package)
        o = self._shared_pkg_cache.get(key, None)
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
        try:
            return [atom.atom(x.strip())
                for x in iter_read_bash(
                pjoin(self.base, "profiles", "package.mask"))]
        except IOError, i:
            if i.errno != errno.ENOENT:
                raise
            del i
            return []


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

        configured.tree.__init__(self, raw_repo, self.config_wrappables)
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
        immutable, enabled = self._get_pkg_use(pkg)
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
