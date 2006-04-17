# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import prototype, errors

class tree(prototype.tree):
	def __init__(self, *trees):
		super(tree,self).__init__()
		for x in trees:
			if not isinstance(x, prototype.tree):
				raise errors.InitializationError("%s is not a repository tree derivative" % str(x))
		self.trees=trees
		
	def _get_categories(self, *optionalCategory):
		d=set()
		failures=0
		if optionalCategory:
			optionalCategory=optionalCategory[0]
			for x in self.trees:
				try:
					map(d.add, x.categories[optionalCategory])
				except KeyError:
					failures+=1
		else:
			for x in self.trees:
				try:
					map(d.add, x.categories)
				except (errors.TreeCorruption, KeyError):
					failures+=1
		if failures == len(self.trees):
			if optionalCategory:
				raise KeyError("category base '%s' not found" % str(optionalCategory))
			raise KeyError("failed getting categories")
		return tuple(d)

	def _get_packages(self, category):
		d = set()
		failures=0
		for x in self.trees:
			try:
				map(d.add, x.packages[category])
			except (errors.TreeCorruption, KeyError):
				failures+=1
		if failures == len(self.trees):
			raise KeyError("category '%s' not found" % category)
		return tuple(d)

	def _get_versions(self,package):
		d = set()
		failures=0
		for x in self.trees:
			try:
				map(d.add, x.versions[package])
			except (errors.TreeCorruption, KeyError):
				failures+=1

		if failures == len(self.trees):
			raise KeyError("category '%s' not found" % package)
		return tuple(d)

	def itermatch(self, atom):
		s = set()
		for t in self.trees:
			for m in t.itermatch(atom):
				if m not in s:
					yield m
					s.add(m)

	def __iter__(self):
		s = set()
		for t in self.trees:
			# rather then using the iter, we use version scanning
			# reason is wee only need to cache the cpv, not the full obj.
			for cpv in t.versions:
				if cpv not in s:
					yield t.package_class(cpv)
					s.add(cpv)

	def __getitem__(self, key):
		for t in self.trees:
			try:
				p = t[key]
				return p
			except KeyError:
				pass
		# made it here, no match.
		raise KeyError("package %s not found" % key)
