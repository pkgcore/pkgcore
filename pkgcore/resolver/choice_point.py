# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.compatibility import any
from pkgcore.util.lists import stable_unique
from pkgcore.util.iterables import caching_iter
import operator

class CheatingIter(object):
	__slots__ = ("_src", "_position", "_item", "_iter_obj")
	def __init__(self, bool_restrict_instance):
		self._src = bool_restrict_instance
		self._position = -1
		self._item = None
		self._iter_obj = None
		
	def __getitem__(self, idx):
		if idx < 0:
			raise IndexError("piss off, I don't like negative indexes")
		elif idx < self._position or self._position == -1:
			self._iter_obj = self._src.iter_dnf_solutions()
			self._position = -1

		if idx != self._position:
			try:
				for x in xrange(idx - self._position):
					item = self._iter_obj.next()
			except StopIteration:
				self._position = -1
				raise IndexError
			self._item = stable_unique(item)
			self._position = idx
		return self._item
		
	def __iter__(self):
		return self._src.iter_dnf_solutions()

class choice_point(object):

	__slots__ = ("__weakref__", "atom", "matches", "matches_idx", "solution_filters",
		"_rdep_solutions", "_dep_solutions", "_provides_solutions")
	
	depends_getter = operator.attrgetter("depends")
	rdepends_getter = operator.attrgetter("rdepends")
	provides_getter = operator.attrgetter("provides")

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

		if self.matches_idx is None:
			raise IndexError("no solutions remain")
		if hasattr(atom, "__contains__") and not isinstance(atom, basestring):
			self.solution_filters.update(atom)
		else:
			self.solution_filters.add(atom)

		# ref copies; grab this info now before we screw with the stack
		orig_dep, orig_rdep = self.depends, self.rdepends
		orig_provides = self.provides

		# lock step checks of each- it's possible for rdepend to push depend forward
		rdep_idx = orig_match_idx = -1
		try:
			while orig_match_idx != self.matches_idx:
				orig_match_idx = self.matches_idx
				while any(True for x in self.depends if x in self.solution_filters):
					self._dep_solutions[1] += 1

				# optimization.  don't redo rdep if it forced last redo, and matches hasn't changed
				if rdep_idx != self.matches_idx:
					while any(True for x in self.rdepends if x in self.solution_filters):
						self._rdep_solutions[1] += 1
				rdep_idx = self.matches_idx
		except IndexError:
			# shot off the end, no solutions remain
			self.matches_idx = None
			return set(orig_dep + orig_rdep), orig_provides

		s = set(self.depends + self.rdepends)
		s.difference_update(orig_dep + orig_rdep)
		return s, [x for x in self.provides if x not in orig_provides]

	def _common_property(self, existing, getter):
		# are we beyond this matches solutions?
		ret = None
		if self.matches_idx == existing[0]:
			try:
				return existing[2][existing[1]]
			except IndexError:
				self.matches_idx = self.matches_idx + 1
		elif self.matches_idx is None:
			raise IndexError
		existing[0:3] = [self.matches_idx, 0,
			CheatingIter(getter(self.matches[self.matches_idx]))]
		return existing[2][existing[1]]

	@property
	def current_pkg(self):
		# trigger depends lookup.  cheap, but works.
		self.depends, self.rdepends
		return self.matches[self.matches_idx]

	def force_next_pkg(self):
		if bool(self):
			self.matches_idx = self.matches_idx + 1
			return bool(self)
		return False

	@property
	def depends(self):
		return self._common_property(self._dep_solutions, self.depends_getter)

	@property
	def rdepends(self):
		return self._common_property(self._rdep_solutions, self.rdepends_getter)

	@property
	def provides(self):
		return self._common_property(self._provides_solutions, self.provides_getter)

	def __nonzero__(self):
		if self.matches_idx is not None:
			try:
				self.depends
				self.rdepends
			except IndexError:
				return False
			return True
		return False

	def clone(self):
		o = self.__class__(self.atom, self.matches)
		o.matches_idx = self.matches_idx
		o.matches_len = self.matches_len
		o.solutions_filter.update(self.solutions_filter)
		o._dep_solutions = self._dep_solutions[:]
		o._rdep_solutions = self._rdep_solutions[:]
		o._provides_solutions = self._provides_solutions[:]
