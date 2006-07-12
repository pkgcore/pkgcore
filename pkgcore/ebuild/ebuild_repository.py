# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
ebuild repository, specific to gentoo ebuild trees (whether cvs or rsync)
"""

import os, stat
from pkgcore.repository import prototype, errors, configured
from pkgcore.util.containers import InvertedContains
from pkgcore.util.file import read_dict
from pkgcore.util import currying
from pkgcore.util.demandload import demandload
demandload(globals(), "pkgcore.ebuild.ebd:buildable")

from pkgcore.plugins import get_plugin

metadata_offset = "profiles"

class UnconfiguredTree(prototype.tree):

	"""
	raw implementation supporting standard ebuild tree, return packages don't have USE configuration bound to them
	"""
	
	false_categories = frozenset(["eclass", "profiles", "packages", "distfiles", 
		"licenses", "scripts", "CVS", ".svn"])
	configured = False
	configurables = ("settings",)
	configure = None
	ebuild_format_magic = "ebuild_src"

	def __init__(self, location, cache=None, eclass_cache=None, mirrors_file=None, default_mirrors=None):

		"""
		@param location: on disk location of the tree
		@param cache: sequence of L{pkgcore.cache.template.database} instances to use for storing metadata
		@param eclass_cache: If not None, L{pkgcore.ebuild.eclass_cache} instance representing the eclasses available,
		if None, generates the eclass_cache itself
		@param mirrors_file: file parsed via L{read_dict} to get mirror tiers
		@param default_mirrors: Either None, or sequence of mirrors to try fetching from first, then falling back to other uri
		"""
		
		super(UnconfiguredTree, self).__init__()
		self.base = self.location = location
		try:
			st = os.lstat(self.base)
			if not stat.S_ISDIR(st.st_mode):
				raise errors.InitializationError("base not a dir: %s" % self.base)

		except OSError:
			raise errors.InitializationError("lstat failed on base %s" % self.base)
		if eclass_cache is None:
			import eclass_cache
			self.eclass_cache = eclass_cache.cache(self.base)
		else:
			self.eclass_cache = eclass_cache
		if mirrors_file:
			mirrors = read_dict(os.path.join(self.base, metadata_offset, "thirdpartymirrors"))
		else:
			mirrors = {}
		fp = os.path.join(self.base, metadata_offset, "thirdpartymirrors")
		if os.path.exists(fp):
			from random import shuffle
			f = None
			try:
				f = open(os.path.join(self.base, metadata_offset, "thirdpartymirrors"), "r")
				for k, v in read_dict(f, splitter="\t", source_isiter=True).items():
					v = v.split()
					shuffle(v)
					mirrors.setdefault(k, []).extend(v)
			except OSError:
				if f is not None:
					f.close()
				raise

		if isinstance(cache, tuple):
			cache = list(cache)
		elif not isinstance(cache, list):
			cache = [cache]	

		self.mirrors = mirrors
		self.default_mirrors = default_mirrors
		self.cache = cache
		self.package_class = get_plugin("format", self.ebuild_format_magic)(self, cache, self.eclass_cache, self.mirrors, self.default_mirrors)

	def rebind(self, **kwds):

		"""
		generate a new tree instance with the same location using supplied keywords
		
		@param kwds: see __init__ for valid values
		"""
		
		o = self.__class__(self.location, **kwds)
		o.categories = self.categories
		o.packages = self.packages
		o.versions = self.versions
		return o

	def _get_categories(self, *optionalCategory):
		# why the auto return?  current porttrees don't allow/support categories deeper then one dir.
		if len(optionalCategory):
			#raise KeyError
			return ()

		try:	
			return tuple(x for x in os.listdir(self.base) \
				if stat.S_ISDIR(os.lstat(os.path.join(self.base, x)).st_mode) 
				and x not in self.false_categories)
		except (OSError, IOError), e:
			raise KeyError("failed fetching categories: %s" % str(e))

	def _get_packages(self, category):
		cpath = os.path.join(self.base,category.lstrip(os.path.sep))
		try:	
			return tuple(x for x in os.listdir(cpath) \
				if stat.S_ISDIR(os.lstat(os.path.join(cpath, x)).st_mode))

		except (OSError, IOError), e:
			raise KeyError("failed fetching packages for category %s: %s" % \
					(os.path.join(self.base, category.lstrip(os.path.sep)), \
					str(e)))

	def _get_versions(self, catpkg):
		pkg = catpkg.split("/")[-1]
		cppath = os.path.join(self.base, catpkg.lstrip(os.path.sep))
		# 7 == len(".ebuild")
		try:
			return tuple(x[len(pkg):-7].lstrip("-") 
				for x in os.listdir(cppath) \
				if x.endswith(".ebuild") and x.startswith(pkg) and  \
				stat.S_ISREG(os.lstat(os.path.join(cppath, x)).st_mode))
		except (OSError, IOError), e:
			raise KeyError("failed fetching versions for package %s: %s" % \
				(os.path.join(self.base, catpkg.lstrip(os.path.sep)), str(e)))

	def _get_ebuild_path(self, pkg):
		return os.path.join(self.base, pkg.category, pkg.package, \
			"%s-%s.ebuild" % (pkg.package, pkg.fullver))


class ConfiguredTree(configured.tree):

	"""
	wrapper around a L{UnconfiguredTree}, binding USE configuration data (in general, all build/configuration data)
	"""

	configurable = "use"
	config_wrappables = dict((x, currying.alias_class_method("evaluate_depset")) for x in
		["depends", "rdepends", "fetchables", "license", "src_uri", "license", "provides"])

	def __init__(self, raw_repo, domain_settings, fetcher=None):
		"""
		@param raw_repo: L{UnconfiguredTree} instance
		@param domain_settings: environment settings to bind
		@param fetcher: L{pkgcore.fetch.base.fetcher} instance to use for getting access to fetchable files
		"""
		if "USE" not in domain_settings:
			raise errors.InitializationError("%s requires the following settings: '%s', not supplied" % (str(self.__class__), x))

		configured.tree.__init__(self, raw_repo, self.config_wrappables)
		self.default_use = tuple(domain_settings["USE"])
		self.domain_settings = domain_settings
		if fetcher is None:
			self.fetcher = self.domain_settings["fetcher"]
		else:
			self.fetcher = fetcher
		self.eclass_cache = self.raw_repo.eclass_cache

	def _get_pkg_kwds(self, pkg):
		return {"initial_settings":self.default_use,
			"unchangable_settings":InvertedContains(pkg.iuse),
			"build_callback":self.generate_buildop}

	def generate_buildop(self, pkg):
		return buildable(pkg, self.domain_settings, self.eclass_cache, self.fetcher)

UnconfiguredTree.configure = ConfiguredTree
