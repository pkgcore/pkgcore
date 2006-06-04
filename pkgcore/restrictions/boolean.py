# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
This module provides classes that can be used to combine arbitrary collections of restrictions in AND, NAND, OR, NOR, XOR, XNOR
style operations.
"""

__all__ = ("AndRestriction", "OrRestriction", "XorRestriction")

from itertools import islice
from pkgcore.util.compatibility import any, all
import restriction


class base(restriction.base):
	__slots__ = ("restrictions", "type")

	def __init__(self, *restrictions, **kwds):
		"""Optionally hand in (positionally) restrictions to use as the basis of this restriction
		finalize=False, set it to True to notify this instance to internally finalize itself (no way to reverse it yet)
		negate=False, controls whether matching results are negated
		finalize=False, controls whether this instance is finalized.
		node_type=None, controls whether to override the class default (if specified); no type in class nor passed in means
		no filtering of add_restriction calls.
		"""
		if "node_type" in kwds:
			self.type = kwds["node_type"]
		finalize = kwds.pop("finalize", False)
		super(base, self).__init__(negate=kwds.get("negate", False))

		self.restrictions = []
		if restrictions:
			self.add_restriction(*restrictions)

		if finalize:
			self.restrictions = tuple(self.restrictions)

	def change_restrictions(self, *restrictions, **kwds):
		if self.__class__.type != self.type:
			kwds["node_type"] = self.type
		kwds["negate"] = self.negate
		return self.__class__(*restrictions, **kwds)

	def add_restriction(self, *new_restrictions):
		"""add restriction(s), must be isinstance of required_base
		"""
		if not new_restrictions:
			raise TypeError("need at least one restriction handed in")
		if hasattr(self, "type"):
			try:
				for r in new_restrictions:
					if r.type is not None and r.type != self.type:
						raise TypeError("instance '%s' is restriction type '%s', must be '%s'" % (r, r.type, self.type))
			except AttributeError:
				raise TypeError("type '%s' instance '%s' has no restriction type, '%s' required" % (r.__class__,
					r, getattr(self, "type", "unset")))

		self.restrictions.extend(new_restrictions)

	def finalize(self):
		self.restrictions = tuple(self.restrictions)

	def total_len(self):
		return sum(x.total_len() for x in self.restrictions) + 1

	def __len__(self):
		return len(self.restrictions)

	def __iter__(self):
		return iter(self.restrictions)

	def match(self, action, *vals):
		raise NotImplementedError

	force_False, force_True = match, match

	def solutions(self, full_solution_expansion=False):
		raise NotImplementedError()

	def __getitem__(self, key):
		return self.restrictions[key]


# this beast, handles N^2 permutations.  convert to stack based.
def iterative_quad_toggling(pkg, pvals, restrictions, starting, end, truths, filter, desired_false=None, desired_true=None, kill_switch=None):
	if desired_false == None:
		desired_false = lambda r, a:r.force_False(*a)
	if desired_true == None:
		desired_true = lambda r, a:r.force_True(*a)

#	import pdb;pdb.set_trace()
	reset = True
	if starting == 0:
		if filter(truths):
			yield True
	for index, rest in islice(enumerate(restrictions), starting, end):
		if reset:
			entry = pkg.changes_count()
		reset = False
		if truths[index]:
			if desired_false(rest, pvals):
				reset = True
				t = truths[:]
				t[index] = False
				if filter(t):
					yield True
				for x in iterative_quad_toggling(pkg, pvals, restrictions, index + 1, end, t, filter,
					desired_false=desired_false, desired_true=desired_true, kill_switch=kill_switch):
#					import pdb;pdb.set_trace()
					yield True
				reset = True
			else:
				if kill_switch != None and kill_switch(truths, index):
					return
		else:
			if desired_true(rest, pvals):
				reset = True
				t = truths[:]
				t[index] = True
				if filter(t):
					yield True
				for x in iterative_quad_toggling(pkg, pvals, restrictions, index + 1, end, t, filter,
					desired_false=desired_false, desired_true=desired_true):
#					import pdb;pdb.set_trace()
					yield True
				reset = True
			elif index == end:
				if filter(truths):
#					import pdb;pdb.set_trace()
					yield True
			else:
				if kill_switch != None and kill_switch(truths, index):
					return

		if reset:
			pkg.rollback(entry)


class AndRestriction(base):
	"""Boolean AND grouping of restrictions.  negation is a NAND"""
	__slots__ = ()

	def match(self, vals):
		return all(rest.match(vals) for rest in self.restrictions) != self.negate

	def force_True(self, pkg, *vals):
		pvals = [pkg]
		pvals.extend(vals)
		entry_point = pkg.changes_count()
		# get the simple one out of the way first.
		if not self.negate:
			for r in self.restrictions:
				if not r.force_True(*pvals):
					pkg.rollback(entry_point)
					return False
			return True

		# <insert page long curse here>, NAND logic, len(restrictions)**2 potential solutions.
		# 0|0 == 0, 0|1 == 1|0 == 0|0 == 1.
		# XXX this is quadratic.  patches welcome to dodge the requirement to push through all potential
		# truths.
		truths = [r.match(*pvals) for r in self.restrictions]
		def filter(truths):
			return False in truths

		for x in iterative_quad_toggling(pkg, pvals, self.restrictions, 0, len(self.restrictions), truths, filter):
			return True
		return False

	def force_False(self, pkg, *vals):
		pvals = [pkg]
		pvals.extend(vals)
		entry_point = pkg.changes_count()
		# get the simple one out of the way first.
		if self.negate:
			for r in self.restrictions:
				if not r.force_True(*pvals):
					pkg.rollback(entry_point)
					return False
			return True

		# <insert page long curse here>, NAND logic, (len(restrictions)^2)-1 potential solutions.
		# 1|1 == 0, 0|1 == 1|0 == 0|0 == 1.
		# XXX this is quadratic.  patches welcome to dodge the requirement to push through all potential
		# truths.
		truths = [r.match(*pvals) for r in self.restrictions]
		def filter(truths):
			return False in truths
		for x in iterative_quad_toggling(pkg, pvals, self.restrictions, 0, len(self.restrictions), truths, filter):
			return True
		return False

	def solutions(self, full_solution_expansion=False):
		if self.negate:
			raise NotImplementedError("negation for solutions on AndRestriction isn't implemented yet")

		flattened_matrix = []
		s = []
		for x in self.restrictions:
			if isinstance(x, base):
				s2 = x.solutions(full_solution_expansion=full_solution_expansion)
				# there *must* be a solution returned.
				assert s2
				if len(s2) == 1:
					flattened_matrix.extend(s2[0])
				else:
					s.append(s2)
			else:
				flattened_matrix.append(x)

		# matrix multiplication.
		flattened_matrix = [flattened_matrix]

		for current_s in s:
			flattened_matrix = list(x + y for x in current_s for y in flattened_matrix)

		return flattened_matrix


	def __str__(self):
		if self.negate:
			return "not ( %s )" % " && ".join(str(x) for x in self.restrictions)
		return "( %s )" % " && ".join(str(x) for x in self.restrictions)


class OrRestriction(base):
	"""Boolean OR grouping of restrictions."""
	__slots__ = ()

	def match(self, vals):
		return any(rest.match(vals) for rest in self.restrictions) != self.negate

	def solutions(self, full_solution_expansion=False):
		if self.negate:
			raise NotImplementedError("OrRestriction.solutions doesn't yet support self.negate")
		if not self.restrictions:
			return [[]]
		choices = []
		for x in self.restrictions:
			if isinstance(x, base):
				s = x.solutions(full_solution_expansion=full_solution_expansion)
				# must be a solution.
				assert s
				choices.extend(s)
			else:
				choices.append([x])

		return choices


	def force_True(self, pkg, *vals):
		pvals = [pkg]
		pvals.extend(vals)
		entry_point = pkg.changes_count()
		# get the simple one out of the way first.
		if self.negate:
			for r in self.restrictions:
				if not r.force_False(*pvals):
					pkg.rollback(entry_point)
					return False
			return True

		# <insert page long curse here>, OR logic, len(restrictions)**2-1 potential solutions.
		# 0|0 == 0, 0|1 == 1|0 == 1|1 == 1.
		# XXX this is quadratic.  patches welcome to dodge the requirement to push through all potential
		# truths.
		truths = [r.match(*pvals) for r in self.restrictions]
		def filter(truths):
			return True in truths
		for x in iterative_quad_toggling(pkg, pvals, self.restrictions, 0, len(self.restrictions), truths, filter):
			return True
		return False

	def force_False(self, pkg, *vals):
		pvals = [pkg]
		pvals.extend(vals)
		entry_point = pkg.changes_count()
		# get the simple one out of the way first.
		if not self.negate:
			for r in self.restrictions:
				if not r.force_False(*pvals):
					pkg.rollback(entry_point)
					return
			yield True
			return

		# <insert page long curse here>, OR logic, (len(restrictions)**2)-1 potential solutions.
		# 0|0 == 0, 0|1 == 1|0 == 1|1 == 1.
		# XXX this is quadratic.  patches welcome to dodge the requirement to push through all potential
		# truths.
		truths = [r.match(*pvals) for r in self.restrictions]
		def filter(truths):
			return True in truths
		for x in iterative_quad_toggling(pkg, pvals, self.restrictions, 0, len(self.restrictions), truths, filter):
			yield True


	def __str__(self):
		if self.negate:
			return "not ( %s )" % " || ".join(str(x) for x in self.restrictions)
		return "( %s )" % " || ".join(str(x) for x in self.restrictions)


class XorRestriction(base):
	"""Boolean XOR grouping of restrictions."""
	__slots__ = ()

	def __init__(*a, **kw):
		raise NotImplementedError("kindly don't use xor yet")

	def match(self, vals):
		if not self.restrictions:
			return not self.negate

		if self.negate:
			# 1|1 == 0|0 == 1, 0|1 == 1|0 == 0
			armed = self.restrictions[0].match(*vals)
			for rest in islice(self.restrictions, 1, len(self.restrictions)):
				if armed != rest.match(vals):
					return False
			return True
		# 0|1 == 1|0 == 1, 0|0 == 1|1 == 0
		armed = False
		for rest in self.restrictions:
			if armed == rest.match(vals):
				if armed:
					return False
			else:
				if not armed:
					armed = True
		if armed:
			return True
		return False

	def force_True(self, pkg, *vals):
		pvals = [pkg]
		pvals.extend(vals)
		entry_point = pkg.changes_count()
		truths = [r.match(*pvals) for r in self.restrictions]
		count = truths.count(True)
		# get the simple one out of the way first.
		l = len(truths)
		if self.negate:
			f = lambda r: r.force_False(*pvals)
			t = lambda r: r.force_True(*pvals)
			if count > l/2:	order = ((t, count, True), (f, l - count, False))
			else:			order = ((f, l - count, False), (t, count, True))
			for action, current, desired in order:
				if current == l:
					return True
				for x, r in enumerate(self.restrictions):
					if truths[x] != desired:
						if action(r):
							current += 1
						else:
							break
				if current == l:
					return True
				pkg.rollback(entry_point)
			return False

		stack = []
		for x, val in enumerate(truths):
			falses = filter(None, val)
			if truths[x]:
				falses.remove(x)
				stack.append((falses, None))
			else:
				stack.append((falses, x))

		if count == 1:
			return True
			del stack[truths.index(True)]

		for falses, truths in stack:
			failed = False
			for x in falses:
				if not self.restrictions[x].force_False(*pvals):
					failed = True
					break
			if not failed:
				if trues != None:
					if self.restrictions[x].force_True(*pvals):
						return True
				else:
					return True
			pkg.rollback(entry_point)
		return False

	def force_False(self, pkg, *vals):
		pvals = [pkg]
		pvals.extend(vals)
		entry_point = pkg.changes_count()
		truths = [r.match(*pvals) for r in self.restrictions]
		count = truths.count(True)
		# get the simple one out of the way first.
		l = len(truths)
		if not self.negate:
			f = lambda r: r.force_False(*pvals)
			t = lambda r: r.force_True(*pvals)
			if count > l/2:	order = ((t, count, True), (f, l - count, False))
			else:			order = ((f, l - count, False), (t, count, True))
			for action, current, desired in order:
				if current == l:
					return True

				for x, r in enumerate(self.restrictions):
					if truths[x] != desired:
						if action(r):
							current += 1
						else:
							break
				if current == l:
					return True
				pkg.rollback(entry_point)
			return False
		# the fun one.
		stack = []
		for x, val in enumerate(truths):
			falses = filter(None, val)
			if truths[x]:
				falses.remove(x)
				stack.append((falses, None))
			else:
				stack.append((falses, x))

		if count == 1:
			return True

		for falses, truths in stack:
			failed = False
			for x in falses:
				if not self.restrictions[x].force_False(*pvals):
					failed = True
					break
			if not failed:
				if trues != None:
					if self.restrictions[x].force_True(*pvals):
						return True
				else:
					return True
			pkg.rollback(entry_point)
		return False

	def __str__(self):
		if self.negate:
			return "not ( %s )" % " ^^ ".join(str(x) for x in self.restrictions)
		return "( %s )" % " ^^ ".join(str(x) for x in self.restrictions)
