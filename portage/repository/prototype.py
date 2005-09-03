# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: prototype.py 1965 2005-09-03 02:48:34Z ferringb $

from portage.util.mappings import IndexableSequence
from weakref import proxy
from portage.package.atom import atom

def ix_cat_callable(*cat):
	return "/".join(cat)

class tree(object):
	"""
	del raw_repo, and set it to the underlying repo if you're wrapping another repo"""
	raw_repo = None
	package_class = None
	configured = True
	configure = ()
	
	def __init__(self, frozen=True):
		self.categories = IndexableSequence(self._get_categories, self._get_categories, 
			returnIterFunc=ix_cat_callable, returnEmpty=True, modifiable=(not frozen))
		self.packages   = IndexableSequence(self.categories.iterkeys, self._get_packages, \
			returnIterFunc=lambda x,y: str(x)+"/"+str(y), modifiable=(not frozen))
		self.versions   = IndexableSequence(self.packages.__iter__, self._get_versions, \
			returnIterFunc=lambda x,y: str(x)+"-"+str(y), modifiable=(not frozen))
#		self.raw_repo = proxy(self)
		self.frozen = frozen


	def _get_categories(self, *arg):
		raise NotImplementedError


	def _get_packages(self, category):
		raise NotImplementedError


	def _get_versions(self, package):
		raise NotImplementedError


	def __getitem__(self, cpv):
		cpv_inst = self.package_class(cpv)
		if cpv_inst.fullver not in self.versions[cpv_inst.key]:
			del cpv_inst
			raise KeyError(cpv)
		return cpv_inst


	def __setitem__(self, *values):
		raise AttributeError


	def __delitem__(self, cpv):
		raise AttributeError


	def __iter__(self):
		for cpv in self.versions:
			yield self.package_class(cpv)
		return


	def match(self, atom):
		return list(self.itermatch(atom))


	def itermatch(self, restrict):
		if isinstance(restrict, atom):
			if restrict.category == None:
				candidates = self.packages
			else:
				if restrict.package == None:
					try:	candidates = self.packages[restrict.category]
					except KeyError:
						# just stop now.  no category matches == no yielded cpvs.
						return
				else:
					try:
						if restrict.package not in self.packages[restrict.category]:
							# no matches possible
							return
						candidates = [restrict.key]
					except KeyError:
						# restrict.category wasn't valid.  no matches possible.
						return
		else:
			candidates = self.packages

		#actual matching.
		for catpkg in candidates:
			for ver in self.versions[catpkg]:
				pkg = self.package_class(catpkg+"-"+ver)
				if restrict.match(pkg):
					yield pkg
		return


	def add_package(self, pkg):
		if self.frozen:
			raise AttributeError,"repo is frozen"
		return self._add_new_package(self, pkg)


	def _add_new_package(self, pkg):
		raise NotImplementedError


	def del_package(self, key):
		if self.frozen:
			raise AttributeError,"repo is frozen"
		return self._del_package(self,key)


	def _del_package(self,pkg):
		raise NotImplementedError
