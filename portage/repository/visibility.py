# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

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


	def itermatch(self, atom):
		for cpv in self.raw_repo.itermatch(atom):
			if self.restriction.match(cpv) == self.sentinel_val:
				yield cpv
