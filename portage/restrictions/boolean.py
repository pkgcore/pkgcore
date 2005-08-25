# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: boolean.py 1911 2005-08-25 03:44:21Z ferringb $

"""
This module provides classes that can be used to combine arbitrary collections of restrictions in AND, NAND, OR, NOR, XOR, XNOR 
style operations.
"""

from itertools import imap, islice
from portage.util.iterate import enumerate

__all__ = ("AndRestriction", "OrRestriction", "XorRestriction")
import restriction

class base(restriction.base):
	__slots__ = tuple(["restrictions"] + restriction.base.__slots__)
	required_base = None
	
	def __init__(self, *restrictions, **kwds):
		"""Optionally hand in (positionally) restrictions to use as the basis of this restriction
		finalize=False, set it to True to notify this instance to internally finalize itself (no way to reverse it yet)
		negate=False, controls whether matching results are negated
		"""
		if "finalize" in kwds:
			finalize = kwds["finalize"]
			del kwds["finalize"]
		else:
			finalize = False
		super(base, self).__init__(**kwds)
		for x in restrictions:
			if not isinstance(x, restriction.base):
				#bad monkey.
				raise TypeError, x

		if finalize:
			self.restrictions = tuple(restrictions)
		else:
			self.restrictions = list(restrictions)


	def add_restriction(self, *new_restrictions):
		"""add restriction(s), must be isinstance of required_base
		"""
		if len(new_restrictions) == 0:
			raise TypeError("need at least one restriction handed in")
		for r in new_restrictions:
			if not isinstance(r, self.required_base):
				raise TypeError("instance '%s' isn't a derivative '%s'" % (r, self.required_base))
		
		self.restrictions.extend(new_restrictions)

	def finalize(self):
		self.restrictions = tuple(self.restrictions)

	def total_len(self):	return sum(imap(lambda x: x.total_len(), self.restrictions)) + 1

	def __len__(self):	return len(self.restrictions)

	def __iter__(self):	return iter(self.restrictions)

	def match(self, action, *vals):
		raise NotImplementedError

	force_False, force_True = match, match

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
	for index, rest in enumerate(restrictions, starting, end):
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
	__slots__ = tuple(base.__slots__)

	def match(self, vals):
		if self.negate:
			# 1|1 == 0, 1|0 == 0|1 == 0|0 == 1
			missed = False
			for rest in self.restrictions:
				if not rest.match(vals):
					missed = True
				elif missed:
					return True
			return False
		for rest in self.restrictions:
			if not rest.match(vals):
				return False
		return True
	
	def force_True(self, pkg, *vals):
		pvals = [pkg]
		pvals.extend(vals)
		entry_point = pkg.changes_count()
		# get the simple one out of the way first.
		if not self.negate:
			for r in self.restrictions:
				if not r.force_True(*pvals):
					pkg.rollback(entry_point)
					return
			yield True
			return

		# <insert page long curse here>, NAND logic, len(restrictions)**2 potential solutions.
		# 0|0 == 0, 0|1 == 1|0 == 0|0 == 1.
		# XXX this is quadratic.  patches welcome to dodge the requirement to push through all potential
		# truths.
		truths = [r.match(*pvals) for r in self.restrictions]
		def filter(truths):
			return False in truths
		
		for x in iterative_quad_toggling(pkg, pvals, self.restrictions, 0, len(self.restrictions), truths, filter):
			yield True 

	def force_False(self, pkg, *vals):
		pvals = [pkg]
		pvals.extend(vals)
		entry_point = pkg.changes_count()
		# get the simple one out of the way first.
		if self.negate:
			for r in self.restrictions:
				if not r.force_True(*pvals):
					pkg.rollback(entry_point)
					return
			yield True
			return

		# <insert page long curse here>, NAND logic, (len(restrictions)^2)-1 potential solutions.
		# 1|1 == 0, 0|1 == 1|0 == 0|0 == 1.
		# XXX this is quadratic.  patches welcome to dodge the requirement to push through all potential
		# truths.
		truths = [r.match(*pvals) for r in self.restrictions]
		def filter(truths):
			return False in truths
		for x in iterative_quad_toggling(pkg, pvals, self.restrictions, 0, len(self.restrictions), truths, filter):
			yield True 

	def __str__(self):
		if self.negate:	return "not ( %s )" % " && ".join(imap(str, self.restrictions))
		return "( %s )" % " && ".join(imap(str, self.restrictions))


class OrRestriction(base):
	"""Boolean OR grouping of restrictions."""
	__slots__ = base.__slots__
	
	def match(self, vals):
		if self.negate:
			# 1|1 == 1|0 == 0|1 == 0, 0|0 == 1
			for rest in self.restrictions:
				if rest.match(vals):
					return
			return True
		for rest in self.restrictions:
			if rest.match(vals):
				return True
		return False
	
	def force_True(self, pkg, *vals):
		pvals = [pkg]
		pvals.extend(vals)
		entry_point = pkg.changes_count()
		# get the simple one out of the way first.
		if self.negate:
			for r in self.restrictions:
				if not r.force_False(*pvals):
					pkg.rollback(entry_point)
					return
			yield True
			return

		# <insert page long curse here>, OR logic, len(restrictions)**2-1 potential solutions.
		# 0|0 == 0, 0|1 == 1|0 == 1|1 == 1.
		# XXX this is quadratic.  patches welcome to dodge the requirement to push through all potential
		# truths.
		truths = [r.match(*pvals) for r in self.restrictions]
		def filter(truths):
			return True in truths
		for x in iterative_quad_toggling(pkg, pvals, self.restrictions, 0, len(self.restrictions), truths, filter):
			yield True 


	def force_False(self, pkg, *vals):
		pvals = [pkg]
		pvals.extend(vals)
		entry_point = pkg.changes_count()
		# get the simple one out of the way first.
		if not self.negate:
			for r in self.restrictions:
				if not r.force_False(*vals):
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
		if self.negate:	return "not ( %s )" % " || ".join(imap(str, self.restrictions))
		return "( %s )" % " || ".join(imap(str, self.restrictions))


class XorRestriction(base):
	"""Boolean XOR grouping of restrictions."""
	__slots__ = tuple(base.__slots__)

	def match(self, vals):
		if len(self.restrictions) == 0:
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
					yield True
					continue
				for x, r in enumerate(self.restrictions):
					if truths[x] != desired:
						if action(r):
							current += 1
						else:
							break
				if current == l:
					yield True
				pkg.rollback(entry_point)
			return

		stack = []
		for x, val in enumerate(truths):
			falses = filter(None, val)
			if truths[x]:
				falses.remove(x)
				stack.append((falses, None))
			else:
				stack.append((falses, x))

		if count == 1:
			yield True
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
						yield True
				else:
					yield True
			pkg.rollback(entry_point)
		

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
					yield True
					continue
				for x, r in enumerate(self.restrictions):
					if truths[x] != desired:
						if action(r):
							current += 1
						else:
							break
				if current == l:
					yield True
				pkg.rollback(entry_point)
			return
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
			yield True
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
						yield True
				else:
					yield True
			pkg.rollback(entry_point)
		

	def __str__(self):
		if self.negate:	return "not ( %s )" % " ^^ ".join(imap(str, self.restrictions))
		return "( %s )" % " ^^ ".join(imap(str, self.restrictions))


