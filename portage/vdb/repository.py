# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: repository.py 2285 2005-11-10 00:36:17Z ferringb $

import os,stat
from portage.repository import prototype, errors

#needed to grab the PN
from portage.package.cpv import CPV as cpv
from portage.util.lists import unique
from portage.util.mappings import LazyValDict
from portage.util.fs import FsLock
from portage.vdb.contents import ContentsFile
from portage.plugins import get_plugin

class tree(prototype.tree):
	ebuild_format_magic = "ebuild_built"
	
	def __init__(self, location):
		super(tree,self).__init__()
		self.base = self.location = location
		try:
			st = os.lstat(self.base)
			if not stat.S_ISDIR(st.st_mode):
				raise errors.InitializationError("base not a dir: %s" % self.base)
			elif not st.st_mode & (os.X_OK|os.R_OK):
				raise errors.InitializationError("base lacks read/executable: %s" % self.base)

		except OSError:
			raise errors.InitializationError("lstat failed on base %s" % self.base)

		self.package_class = get_plugin("format", self.ebuild_format_magic)(self)
		self.lock = FsLock(self.base)


	def _get_categories(self, *optionalCategory):
		# return if optionalCategory is passed... cause it's not yet supported
		if len(optionalCategory):
			return {}
#		self.lock.acquire_read_lock()
		try:
			try:	return tuple([x for x in os.listdir(self.base) \
				if stat.S_ISDIR(os.lstat(os.path.join(self.base,x)).st_mode)])

			except (OSError, IOError), e:
				raise KeyError("failed fetching categories: %s" % str(e))
		finally:
#			self.lock.release_read_lock()
			pass

	def _get_packages(self, category):
		cpath = os.path.join(self.base,category.lstrip(os.path.sep))
		l=set()
#		self.lock.acquire_read_lock()
		try:
			try:
				for x in os.listdir(cpath):
					if stat.S_ISDIR(os.stat(os.path.join(cpath,x)).st_mode) and not x.endswith(".lockfile"):
						l.add(cpv(x).package)
				return tuple(l)

			except (OSError, IOError), e:
				raise KeyError("failed fetching packages for category %s: %s" % \
				(os.path.join(self.base,category.lstrip(os.path.sep)), str(e)))
		finally:
#			self.lock.release_read_lock()
			pass

	def _get_versions(self, catpkg):
		pkg = catpkg.split("/")[-1]
		l=set()
#		self.lock.acquire_read_lock()
		try:
			try:
				cpath=os.path.join(self.base, os.path.dirname(catpkg.lstrip("/").rstrip("/")))
				for x in os.listdir(cpath):
					# XXX: This matches foo to foo-bar-1.2.3 and creates an incorrect foo-1.2.3 in l
					# This sucks.  fix...
					if x.startswith(pkg) and x[len(pkg)+1].isdigit() and stat.S_ISDIR(os.stat(os.path.join(cpath,x)).st_mode) \
						and not x.endswith(".lockfile"):
						l.add(cpv(x).fullver)
				return tuple(l)
			except (OSError, IOError), e:
				raise KeyError("failed fetching packages for package %s: %s" % \
				(os.path.join(self.base,catpkg.lstrip(os.path.sep)), str(e)))
		finally:
#			self.lock.release_read_lock()
			pass

	def _get_ebuild_path(self, pkg):
		s = "%s-%s" % (pkg.package, pkg.fullver)
		return os.path.join(self.base, pkg.category, s, s+".ebuild")

	def _get_metadata(self, pkg):
		path = os.path.dirname(pkg.path)
		try:
			keys = filter(lambda x: x.isupper() and stat.S_ISREG(os.stat(path+os.path.sep+x).st_mode), os.listdir(path))
		except OSError:
			return None

		def load_data(key):
			if key != "CONTENTS":
				try:
					f = open(os.path.join(path, key))
				except OSError:
					return None
				data = f.read()
				f.close()
				data = data.strip()
				if key == "USE":
					# This is innefficient.
					# it's implemented as a hack here, rather then in the general ebuild_built code however.
					try:
						iuse = set(load_data("IUSE").split())
						data = " ".join(filter(lambda x: x in iuse, data.split()))
					except OSError:
						pass
				
			else:
				data = ContentsFile(os.path.join(path,key))
			return data


		return LazyValDict(keys, load_data)

