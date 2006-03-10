# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2
# $Id: ebuild_repository.py 2273 2005-11-10 00:22:02Z ferringb $

import os, stat
from portage.ebuild.ebd import buildable
from weakref import proxy
from portage.package.conditionals import PackageWrapper
from portage.repository import prototype, errors
from portage.util.mappings import InvertedContains
from portage.util.file import read_dict
from portage.plugins import get_plugin
from portage.util.modules import load_attribute

metadata_offset = "profiles"

def convert_depset(instance, conditionals):
	return instance.evaluate_depset(conditionals)

class UnconfiguredTree(prototype.tree):
	false_categories = set(["eclass","profiles","packages","distfiles","licenses","scripts", "CVS"])
	configured=False
	configurables = ("settings",)
	configure = None
	ebuild_format_magic = "ebuild_src"

	def __init__(self, location, cache=None, eclass_cache=None, mirrors_file=None):
		super(UnconfiguredTree, self).__init__()
		self.base = self.location = location
		try:
			st = os.lstat(self.base)
			if not stat.S_ISDIR(st.st_mode):
				raise errors.InitializationError("base not a dir: %s" % self.base)
			elif not st.st_mode & (os.X_OK|os.R_OK):
				raise errors.InitializationError("base lacks read/executable: %s" % self.base)

		except OSError:
			raise errors.InitializationError("lstat failed on base %s" % self.base)
		if eclass_cache == None:
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
				if f != None:
					f.close()
				raise

		self.mirrors = mirrors
		self.package_class = get_plugin("format", self.ebuild_format_magic)(self, cache, self.eclass_cache, self.mirrors)


	def _get_categories(self, *optionalCategory):
		# why the auto return?  current porttrees don't allow/support categories deeper then one dir.
		if len(optionalCategory):
			#raise KeyError
			return ()

		try:	return tuple([x for x in os.listdir(self.base) \
			if stat.S_ISDIR(os.lstat(os.path.join(self.base,x)).st_mode) and x not in self.false_categories])

		except (OSError, IOError), e:
			raise KeyError("failed fetching categories: %s" % str(e))


	def _get_packages(self, category):

		cpath = os.path.join(self.base,category.lstrip(os.path.sep))
		try:	return tuple([x for x in os.listdir(cpath) \
			if stat.S_ISDIR(os.lstat(os.path.join(cpath,x)).st_mode)])

		except (OSError, IOError), e:
			raise KeyError("failed fetching packages for category %s: %s" % \
			(os.path.join(self.base,category.lstrip(os.path.sep)), str(e)))


	def _get_versions(self, catpkg):

		pkg = catpkg.split("/")[-1]
		cppath = os.path.join(self.base, catpkg.lstrip(os.path.sep))
		# 7 == len(".ebuild")
		try:	return tuple([x[len(pkg):-7].lstrip("-") for x in os.listdir(cppath) \
			if x.endswith(".ebuild") and x.startswith(pkg) and  \
			stat.S_ISREG(os.lstat(os.path.join(cppath,x)).st_mode)])

		except (OSError, IOError), e:
			raise KeyError("failed fetching versions for package %s: %s" % \
			(os.path.join(self.base,catpkg.lstrip(os.path.sep)), str(e)))

	def _get_ebuild_path(self, pkg):
		return os.path.join(self.base, pkg.category, pkg.package, \
			"%s-%s.ebuild" % (pkg.package, pkg.fullver))
		           


class ConfiguredTree(UnconfiguredTree):
	configured = True
	l=["license","depends","rdepends","bdepends", "fetchables", "license", "slot", "src_uri"]
	wrappables = dict(zip(l, len(l)*[convert_depset]))

	def __init__(self, raw_repo, domain_settings, fetcher=None):
		if "USE" not in domain_settings:
			raise errors.InitializationError("%s requires the following settings: '%s', not supplied" % (str(self.__class__), x))

		self.default_use = domain_settings["USE"][:]
		self.domain_settings = domain_settings
		if fetcher == None:
			self.fetcher = self.domain_settings["fetcher"]
		else:
			self.fetcher = fetcher
		self.raw_repo = raw_repo
		r = raw_repo
		self.eclass_cache = self.raw_repo.eclass_cache

	def package_class(self, *a):
		pkg = self.raw_repo.package_class(*a)
		return PackageWrapper(pkg, "use", initial_settings=self.default_use, unchangable_settings=InvertedContains(pkg.data["IUSE"]), 
			attributes_to_wrap=self.wrappables, build_callback=self.generate_buildop)

	def __getattr__(self, attr):
		return getattr(self.raw_repo, attr)

	def generate_buildop(self, pkg):
		return buildable(pkg, self.domain_settings, self.eclass_cache, self.fetcher)

UnconfiguredTree.configure = ConfiguredTree
