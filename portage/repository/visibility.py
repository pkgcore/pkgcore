# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: visibility.py 2278 2005-11-10 00:25:26Z ferringb $

# icky.
# ~harring
import prototype, errors
from portage.restrictions.restriction import base

class filterTree(prototype.tree):
	"""wrap an existing repository filtering results based upon passed in restrictions."""
	def __init__(self, repo, restriction, sentinel_val=False):
		self.raw_repo = repo
		self.sentinel_val = sentinel_val
		if not isinstance(self.raw_repo, prototype.tree):
			raise errors.InitializationError("%s is not a repository tree derivative" % str(self.raw_repo))
		if not isinstance(restriction, base):
			raise errors.InitializationError("%s is not a restriction" % str(restriction)) 
		self.restriction = restriction
		self.raw_repo = repo

	def itermatch(self, atom):
		# note that this lets the repo do the initial filtering.
		# better design would to analyze the restrictions, and inspect the repo,
		# determine what can be done without cost (determined by repo's attributes)
		# versus what does cost (metadata pull for example).
		for cpv in self.raw_repo.itermatch(atom):
			if self.restriction.match(cpv) == self.sentinel_val:
				yield cpv

	def __getattr__(self, key):
		return getattr(self.raw_repo, key)
