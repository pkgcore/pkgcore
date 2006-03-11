# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2
# $Id: repository.py 2269 2005-11-10 00:15:56Z ferringb $

import os,stat
from portage.repository import prototype, errors

#needed to grab the PN
from portage.package.cpv import CPV as cpv

class tree(prototype.tree):
	package_class = str
	def __init__(self, location):
		super(tree,self).__init__()
		self.base = location
		try:
			st = os.lstat(self.base)
			if not stat.S_ISDIR(st.st_mode):
				raise errors.InitializationError("base not a dir: %s" % self.base)
			elif not st.st_mode & (os.X_OK|os.R_OK):
				raise errors.InitializationError("base lacks read/executable: %s" % self.base)

		except OSError:
			raise errors.InitializationError("lstat failed on base %s" % self.base)


	def _get_categories(self, *optionalCategory):
		# return if optionalCategory is passed... cause it's not yet supported
		if optionalCategory:
			return {}

		try:	return tuple([x for x in os.listdir(self.base) \
			if stat.S_ISDIR(os.lstat(os.path.join(self.base,x)).st_mode) and x != "All"])

		except (OSError, IOError), e:
			raise KeyError("failed fetching categories: %s" % str(e))
	
	def _get_packages(self, category):
		cpath = os.path.join(self.base,category.lstrip(os.path.sep))
		#-5 == len(".tbz2")
		l=set()
		try:    
			for x in os.listdir(cpath):
				if x.endswith(".tbz2"):
					l.add(cpv(x[:-5]).package)
			return tuple(l)

		except (OSError, IOError), e:
			raise KeyError("failed fetching packages for category %s: %s" % \
			(os.path.join(self.base,category.lstrip(os.path.sep)), str(e)))

	def _get_versions(self, catpkg):
		pkg = catpkg.split("/")[-1]
		l=set()
		try:
			for x in os.listdir(os.path.join(self.base, os.path.dirname(catpkg.lstrip("/").rstrip("/")))):
				# startswith is faster but causes false positives, fex: mozilla and mozilla-launcher
				if cpv(x[:-5]).package==pkg:
					l.add(cpv(x[:-5]).fullver)
			return tuple(l)
		except (OSError, IOError), e:
			raise KeyError("failed fetching packages for package %s: %s" % \
			(os.path.join(self.base,catpkg.lstrip(os.path.sep)), str(e)))
			
