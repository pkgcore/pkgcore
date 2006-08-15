# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
binpkg ebuild repository
"""

import os, stat, errno
from pkgcore.repository import prototype, errors

#needed to grab the PN
from pkgcore.package.cpv import CPV as cpv
from pkgcore.util.currying import pre_curry
from pkgcore.plugins import get_plugin
from pkgcore.interfaces.data_source import local_source
from pkgcore.util.demandload import demandload
demandload(globals(), "logging time pkgcore.vdb.contents:ContentsFile")
from pkgcore.util.mappings import IndeterminantDict
from pkgcore.binpkg.xpak import Xpak
from pkgcore.binpkg.tar import generate_contents

class tree(prototype.tree):
	ebuild_format_magic = "ebuild_built"	
	# yes, the period is required.  no, do not try and remove it (harring says it stays)
	extension = ".tbz2"
	
	def __init__(self, location):
		super(tree, self).__init__()
		self.base = location
		self._versions_tmp_cache = {}
		try:
			st = os.lstat(self.base)
			if not stat.S_ISDIR(st.st_mode):
				raise errors.InitializationError("base not a dir: %s" % self.base)
			elif not st.st_mode & (os.X_OK|os.R_OK):
				raise errors.InitializationError("base lacks read/executable: %s" % self.base)

		except OSError:
			raise errors.InitializationError("lstat failed on base %s" % self.base)

		self.package_class = get_plugin("format", self.ebuild_format_magic)(self)

	def _get_categories(self, *optionalCategory):
		# return if optionalCategory is passed... cause it's not yet supported
		if optionalCategory:
			return {}
		try:
			try:	
				return tuple(x for x in os.listdir(self.base) \
					if stat.S_ISDIR(os.lstat(os.path.join(self.base, x)).st_mode) and x.lower() != "all")
			except (OSError, IOError), e:
				raise KeyError("failed fetching categories: %s" % str(e))
		finally:
			pass

	def _get_packages(self, category):
		cpath = os.path.join(self.base, category.lstrip(os.path.sep))
		l = set()
		d = {}
		lext = len(self.extension)
		try:
			for x in os.listdir(cpath):
				# don't use lstat; symlinks may exist
				if x.endswith(".lockfile") or not stat.S_ISREG(os.stat(os.path.join(cpath, x)).st_mode) \
					or not x[-lext:].lower() == self.extension:
					continue
				x = cpv(category+"/"+x[:-lext])
				l.add(x.package)
				d.setdefault(category+"/"+x.package, []).append(x.fullver)
		except (OSError, IOError), e:
			raise KeyError("failed fetching packages for category %s: %s" % \
			(os.path.join(self.base, category.lstrip(os.path.sep)), str(e)))

		self._versions_tmp_cache.update(d)
		return tuple(l)

	def _get_versions(self, catpkg):
		return tuple(self._versions_tmp_cache.pop(catpkg))

	def _get_path(self, pkg):
		s = "%s-%s" % (pkg.package, pkg.fullver)
		return os.path.join(self.base, pkg.category, s+".tbz2")
	_get_ebuild_path = _get_path

	_metadata_rewrites = {"depends":"DEPEND", "rdepends":"RDEPEND", "use":"USE", "eapi":"EAPI", "CONTENTS":"contents"}

	def _get_metadata(self, pkg):
		return IndeterminantDict(pre_curry(self._internal_load_key, pkg, Xpak(self._get_path(pkg))))

	def _internal_load_key(self, pkg, xpak, key):
		key = self._metadata_rewrites.get(key, key)
		if key == "contents":
			data = generate_contents(self._get_path(pkg))
		elif key == "environment":
			raise NotImplementedError
			fp = os.path.join(path, key)
			if not os.path.exists(fp):
				if not os.path.exists(fp+".bz2"):
					# icky.
					raise KeyError("environment: no environment file found")
				fp += ".bz2"
			data = local_source(fp)
		else:
			try:
				data = xpak[key]
			except KeyError:
				data =''
		return data

