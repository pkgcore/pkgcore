# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: ebuild_repository.py 1911 2005-08-25 03:44:21Z ferringb $

import os, stat
import ebuild_package
from buildable import buildable
from weakref import proxy
from portage.package.conditionals import PackageWrapper
from portage.repository import prototype, errors
from portage.util.mappings import InvertedContains

def convert_depset(instance, conditionals):
	return instance.evaluate_depset(conditionals)


class UnconfiguredTree(prototype.tree):
	false_categories = set(["eclass","profiles","packages","distfiles","licenses","scripts"])
	configured=False
	configurables = ("settings",)
	configure = None
	def __init__(self, location, cache=None, eclass_cache=None):
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
		self.package_class = ebuild_package.EbuildFactory(self, cache, self.eclass_cache).new_package


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


class ConfiguredTree(UnconfiguredTree):
	configured = True
	l=["license","depends","rdepends","bdepends", "fetchables", "license", "slot", "src_uri"]
	wrappables = dict(zip(l, len(l)*[convert_depset]))

	def __init__(self, raw_repo, domain_settings):
		if "USE" not in domain_settings:
			raise errors.InitializationError("%s requires the following settings: '%s', not supplied" % (str(self.__class__), x))

		self.default_use = domain_settings["USE"][:]
		self.domain_settings = domain_settings
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
		return buildable(pkg, self.domain_settings, self.eclass_cache)

UnconfiguredTree.configure = ConfiguredTree
