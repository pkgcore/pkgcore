# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import warnings
from itertools import imap

common_solution_atoms_barrier = 1
depends_solution_space = "depends"
rdepends_solution_space = "rdepends"

class solution_space(object):
	def __init__(self, pkg, deset_type, solutions):
		assert solutions
		self.atom, self.depset_type, self.solutions = atom, depset_type, solutions
		
		self.solution_index = 0
		self._absolute_atoms = None
	
	@property
	def common_atoms(self):
		if self._common_atoms is None:
			if len(self.solutions) == 1:
				common = tuple(self.solutions)
				self.solutions = ()
			else:
				i = iter(self.solutions)
				common = set(i.next())
				for solution_set in i:
					common = common.intersect(solution_set)
					# not sure how often this is needed really.
					if not common:
						break
				if common:
					# convert solutions to filtered tuples
					self.solutions = tuple([tuple(set(x).difference(common)) for x in self.solutions])
				else:
					# no common base.  convert to tuples.
					self.solutions = map(tuple, self.solutions)
			self._common_atoms = tuple(common)

		return self._common_atoms
	
	@property
	def next_solution(self):
		# folks should have the calling order right.
		assert self._common_atoms is not None
		s = self.solutions[self.solution_index]
		self.solution_index = self.solution_index + 1

		return s
	
	def reset_solutions(self):
		self.solution_index = 0
	
	def __str__(self):
		return "atom(%s): %s" % (self.atom, str(self.solutions))


class state_graph(object):
	
	def __init__(self):
		self.atoms = {}
		self.versionless_packages = {}
		
	def add_node(self, node, child):
		
		
	def add_root_atom(self, atom):
		self.atoms


class resolver(object):
	
	def __init__(self):
		self.graph = state_graph()
		# current decision stack.
		self.stack = []
		self.unresolvable_atoms = set()
		# cp -> pkg
		self.incomplete_truths = {}
		
	def get_unresolved_atom(self):
		yield_it = False
		while self.stack:
			if isinstance(self.stack[-1], solution_space):
				# this package was resolved fully.
				self.stack.pop(-1)
				continue
			elif self.stack[-1] is common_solution_atoms_barrier:
				# ok, so now we expand it.  guranteed solution exists also
				self.stack.pop(-1)
				self.stack.extend(self.stack[-1].next_solution)
				yield_it = True
			else:
				if atom in self.unresolvable_atoms:
					# this should only happen when backtracking?
					import traceback;traceback.print_stack()
					print "uncertain if reachable code point was reached: unresolvable atom was in the stack"
					self.unsolvable_atom(atom)
					continue

				# see if this one is already known.
				yield_it = True
				i = iter(self.graph.versionless_packages.get(atom.package_key, []))
				while yield_it and i:
					if atom.match(x):
						yield_it = False

			if yield_it:
				return self.stack[-1]
			self.stack.pop(-1)

		# else we fell through, no remaining queries.
		return None


	def satisfy_atom(self, atom, matches):
		assert atom not in self.unresolvable_atoms
		assert matches
		assert self.stack
		assert not isinstance(self.stack[-1], solution_space)
		assert atom == self.stack[-1]
		
		
		# no selected solution yet, replace atom with solution space
		s = solution_space(self.stack[-1], matches)
		self.stack.pop(-1)
		self.push_solution_space(s)
		
		
	def unsolvable_atom(self, atom):
		self.unresolvable_atoms.add(atom)
		# remove existant atom, wasn't resolved.
		self.stack.pop(-1)
		self.invalidate_current_solution()
		
		
	def invalidate_current_solution(self):
		# note this can leave earlier decisions in place that may need to be revoked/re-examined.
		# solve this by tracking the mods for this solution space.

		while True:
			if not isinstance(self.stack[-1], solution_space):
				if self.stack[-1] is common_solution_atoms_barrier:

					# roh roh.  this whole solution space is screwed.
					self.stack.pop(-1)

					# sanity check.  barriers should always immediately follow the solution_space
					assert isinstance(self.stack[-1], solution_space)
				self.stack.pop(-1)

			else:
				f = self.stack[-1].next_solution
				if f is None:
					# exhausted all solutions.  non-solvable, force evaluation of
					# next solution in the parent.
					self.stack.pop(-1)
				else:
					# else push the new solution to investigate on the stack.
					self.stack.extend(f)
					break
			# sanity check.  can this occur validly?
			# yes it can, top level atoms without solutions.
			assert self.stack

	def push_solution_space(self, solution):
		common_requirements = solution.common_atoms
		for x in common_requirements:
			if x in self.unresolvable_atoms:
				# well, that solution sucked, and is totally unusable.
				self.invalidate_current_solution()
				return

		self.stack.append(solution)
		# optimization.  push the solution set on directly if no common reqs for the solution space.
		if not common_requirements:
			self.stack.extend(solution.next_solution)
		else:
			# insert the common_barrier so the unresolved_atoms loop can know whether or not
			# to invalidate this solution_space.
			self.stack.append(common_solution_atoms_barrier)
			self.stack.extend(common_requirements)
		

# <harring was bored and hates writing resolver code>
# total slaughter, 
# total slaughter.
# I won't leave...
# a single man alive.
# loddy doddy die,
# genocide.
# loddy doddy daad,
# an ocean of blood.
# lets begin...
# the killing time.
# 
# sad thing?  Almost verbatim from memory of the hang fire episode of trigun ;)
# </harring was bored and hates writing resolver code>
