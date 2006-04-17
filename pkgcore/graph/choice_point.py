# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.compatibility import any, all
from itertools import chain

class choice_point(object):
	
	__slots__ = ("__weakref__", "atom", "matches", "matches_idx", "solution_filters",
		"_rdep_solutions", "_dep_solutions", "_provides_solutions")

	def __init__(self, a, matches):
		self.atom = a
		self.matches = matches
		self.matches_idx = 0
		self.solution_filters = set()
		# match idx, solution idx, solutions
		self._rdep_solutions = [-2, 0, ()]
		self._dep_solutions = [-2, 0, ()]
		self._provides_solutions = [-2, 0, ()]
		
	def reduce_atoms(self, atom):

		if hasattr(atom, "__contains__") and not isinstance(atom, basestring):
			self.solution_filters.update(atom)
		else:
			self.solution_filters.add(atom)

		# ref copies; grab this info now before we screw with the stack
		orig_dep, orig_rdep = self.depends, self.rdepends
		orig_provides = self.provides
		matches_len = len(self.matches)

		# lock step checks of each- it's possible for rdepend to push depend forward
		rdep_idx = orig_match_idx = -1
		try:
			while orig_match_idx != self.matches_idx:
				orig_match_idx = self.matches_idx
				while self.matches_idx < matches_len:
					if all(x not in self.solution_filters for x in self.depends):
						break
					self._dep_solutions[1] += 1

				# optimization.  don't redo rdep if it forced last redo, and matches hasn't changed
				if rdep_idx != self.matches_idx:
					while self.matches_idx < matches_len:
						if all(x not in self.solution_filters for x in self.rdepends):
							break
						self._rdep_solutions[1] += 1
				rdep_idx = self.matches_idx
		except IndexError:
			# shot off the end, no solutions.
			self.matches_idx = matches_len

		if self.matches_idx  == matches_len:
			# no solutions remain.
			return set(orig_dep + orig_rdep), orig_provides

		s = set(self.depends + self.rdepends)
		s.difference_update(orig_dep + orig_rdep)
		return s, [x for x in self.provides if x not in orig_provides]

	def _common_property(self, existing, name):
		# are we beyond this matches solutions?
		if self.matches_idx == existing[0]:
			if existing[1] >= len(existing[2]):
				self.matches_idx = self.matches_idx + 1
		if self.matches_idx != existing[0]:
			existing[0:3] = [self.matches_idx, 0,
				map(tuple, getattr(self.matches[self.matches_idx], name).solutions())]
		return existing[2][existing[1]]
	
	@property
	def current_pkg(self):
		# trigger depends lookup.  cheap, but works.
		self.depends, self.rdepends
		return self.matches[self.matches_idx]
	
	@property
	def depends(self):
		return self._common_property(self._dep_solutions, "depends")

	@property
	def rdepends(self):
		return self._common_property(self._rdep_solutions, "rdepends")

	@property
	def provides(self):
		return self._common_property(self._provides_solutions, "provides")

	def __nonzero__(self):
		l = len(self.matches)
		if self.matches_idx != l:
			try:
				self.depends
				self.rdepends
			except IndexError:
				return False
			return True
		return False

