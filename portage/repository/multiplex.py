# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: multiplex.py 1911 2005-08-25 03:44:21Z ferringb $

import prototype, errors

class tree(prototype.tree):
	def __init__(self, *trees):
		super(tree,self).__init__()
		for x in trees:
			if not isinstance(x, prototype.tree):
				raise errors.InitializationError("%s is not a repository tree derivative" % str(x))
		self.trees=trees
		
	def _get_categories(self, *optionalCategory):
		d={}
		failures=0
		if len(optionalCategory):
			optionalCategory=optionalCategory[0]
			for x in self.trees:
				try:
					for y in x.categories[optionalCategory]:
						d[y] = None
				except KeyError:
					failures+=1
		else:
			for x in self.trees:
				try:
					for y in x.categories:
						d[y] = None
				except (errors.TreeCorruption, KeyError):
					failures+=1
		if failures == len(self.trees):
			if optionalCategory:
				raise KeyError("category base '%s' not found" % str(optionalCategory))
			raise KeyError("failed getting categories")
		return tuple(d.keys())

	def _get_packages(self, category):
		d={}
		failures=0
		for x in self.trees:
			try:
				for y in x.packages[category]:
					d[y] = None
			except (errors.TreeCorruption, KeyError):
				failures+=1
		if failures == len(self.trees):
			raise KeyError("category '%s' not found" % category)
		return tuple(d.keys())

	def _get_versions(self,package):
		d={}
		failures=0
		for x in self.trees:
			try:
				for y in x.versions[package]:
					d[y] = None
			except (errors.TreeCorruption, KeyError):
				failures+=1

		if failures == len(self.trees):
			raise KeyError("category '%s' not found" % package)
		return tuple(d.keys())

	def itermatch(self, atom):
		d={}
		for t in self.trees:
			for m in t.match(atom):
				d[m] = None
		return d.keys()

