# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
repository that combines multiple repositories together
"""

import prototype, errors

class tree(prototype.tree):
	
	"""repository combining multiple repositories into one"""

	def __init__(self, *trees):
		"""
		@param trees: L{pkgcore.repository.prototype.tree} instances to combines into one
		"""
		super(tree, self).__init__()
		for x in trees:
			if not isinstance(x, prototype.tree):
				raise errors.InitializationError("%s is not a repository tree derivative" % str(x))
		self.trees = trees

	def _get_categories(self, *optionalCategory):
		d = set()
		failures = 0
		if optionalCategory:
			optionalCategory = optionalCategory[0]
			for x in self.trees:
				try:
					d.update(x.categories[optionalCategory])
				except KeyError:
					failures += 1
		else:
			for x in self.trees:
				try:
					map(d.add, x.categories)
				except (errors.TreeCorruption, KeyError):
					failures += 1
		if failures == len(self.trees):
			if optionalCategory:
				raise KeyError("category base '%s' not found" % str(optionalCategory))
			raise KeyError("failed getting categories")
		return tuple(d)

	def _get_packages(self, category):
		d = set()
		failures = 0
		for x in self.trees:
			try:
				d.update(x.packages[category])
			except (errors.TreeCorruption, KeyError):
				failures += 1
		if failures == len(self.trees):
			raise KeyError("category '%s' not found" % category)
		return tuple(d)

	def _get_versions(self, package):
		d = set()
		failures = 0
		for x in self.trees:
			try:
				d.update(x.versions[package])
			except (errors.TreeCorruption, KeyError):
				failures += 1

		if failures == len(self.trees):
			raise KeyError("category '%s' not found" % package)
		return tuple(d)

	def itermatch(self, restrict, **kwds):
		return (match for repo in self.trees for match in repo.itermatch(restrict, **kwds))
	itermatch.__doc__ = prototype.tree.itermatch.__doc__.replace("@param", "@keyword").replace("@keyword restrict:", "@param restrict:")

	def __iter__(self):
		return (pkg for repo in self.trees for pkg in repo)

	def __len__(self):
		return sum(len(repo) for repo in self.trees)
		
	def __getitem__(self, key):
		for t in self.trees:
			try:
				p = t[key]
				return p
			except KeyError:
				pass
		# made it here, no match.
		raise KeyError("package %s not found" % key)
