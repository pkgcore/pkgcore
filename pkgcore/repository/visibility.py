# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
filtering repository
"""

# icky.
# ~harring
from pkgcore.repository import prototype, errors
from pkgcore.restrictions.restriction import base

class filterTree(prototype.tree):
	"""wrap an existing repository filtering results based upon passed in restrictions."""
	def __init__(self, repo, restriction, sentinel_val=False):
		self.raw_repo = repo
		self.sentinel_val = sentinel_val
		if not isinstance(self.raw_repo, prototype.tree):
			raise errors.InitializationError(
				"%s is not a repository tree derivative" % (self.raw_repo,))
		if not isinstance(restriction, base):
			raise errors.InitializationError(
				"%s is not a restriction" % (restriction,))
		self.restriction = restriction
		self.raw_repo = repo

	def itermatch(self, restrict, **kwds):
		# note that this lets the repo do the initial filtering.
		# better design would to analyze the restrictions, and inspect the repo,
		# determine what can be done without cost (determined by repo's attributes)
		# versus what does cost (metadata pull for example).
		for cpv in self.raw_repo.itermatch(restrict, **kwds):
			if self.restriction.match(cpv) == self.sentinel_val:
				yield cpv


	itermatch.__doc__ = prototype.tree.itermatch.__doc__.replace(
		"@param", "@keyword").replace("@keyword restrict:", "@param restrict:")

	def __iter__(self):
		for cpv in self.raw_repo:
			if self.restriction.match(cpv) == self.sentinel_val:
				yield cpv

	def __len__(self):
		count = 0
		for x in self:
			count += 1
		return count

	def __getattr__(self, attr):
		return getattr(self.raw_repo, attr)

	def __getitem__(self, key):
		v = self.raw_repo[key]
		if self.restriction.match(v) != self.sentinel_val:
			raise KeyError(key)
		return v
