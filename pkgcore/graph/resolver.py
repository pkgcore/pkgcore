from pkgcore.restrictions import package
from pkgcore.util.iterables import expandable_chain
from pkgcore.util.compatibility import all
from itertools import chain

debug_whitelist = [None]
def debug(msg, id=None):
	if id in debug_whitelist:
		print "debug: %s" % msg

class NoSolution(Exception):
	def __init__(self, msg):
		self.msg = msg
	def __str__(self):
		return str(msg)

class resolver:

	def __init__(self):
		self.search_stacks = [[]]
		self.grab_next_stack()
		self.current_atom = None
		self.false_atoms = set()

	def add_root_atom(self, atom):
		h = hash(atom)
		if h in self.atoms:
			# register a root level stack
			self.ref_stack_for_atom(h, [])
		else:
			self.search_stacks.append([atom])

	def grab_next_stack(self):
		self.current_stack = self.search_stacks[-1]

	def satisfy_atom(self, atom, matches):
		assert atom is self.current_stack[-1]
		# hack since we don't have caching iterable pulling.
		l=list(matches)
		c = choice_point(atom, matches)
		h = hash(atom)
		assert h not in self.atoms
		self.atoms[h] = [c, []]
		# is this right?
		self.ref_stack_for_atom(h, self.current_stack)
		
	def iterate_unresolvable_atoms(self):
		while self.search_stacks:
			assert self.current_stack is self.search_stacks[-1]
			if not self.current_stack:
				self.search_stacks.pop(-1)
				self.grab_next_stack()
				continue

			a = self.current_stack[-1]
			c = self.atoms[a][0]
			t = tuple(self.current_stack)
			for x in c.depends + c.rdepends:
				# yes this is innefficient
				h = hash(x)
				if h not in self.atoms:
					self.current_stack.append(x)
					break
				else:
					#ensure we're registered.
					self.register_stack_for_atom(h, t)
		
			if self.current_stack[-1] is not a:
				# cycle protection.
				if self.current_stack.find(a) != len(self.current_stack) - 1:
					# cycle ask the repo for a pkg configuration that breaks the cycle.
					
					yield package.AndRestriction(
				self.current_atom = a
				yield a
			else:
				# all satisfied.
				self.current_stack.pop(-1)
	
	def unsatisfiable_atom(self, atom, msg="None supplied"):
		# what's on the stack may be different from current_atom; union of atoms will do this fex.
		assert atom is self.current_atom

		a = self.current_atom

		# register this as unsolvable
		self.false_atoms.add(atom)

		bail = none
		istack = expandable_chain(self.atoms[atom][0])
		for stack in istack:
			if not stack:
				# this is a root atom, eg externally supplied. Continue cleanup, but raise.
				bail = NoSolution("root node %s was marked unsatisfiable, reason: %s" % (atom, msg))

			c = self.atoms[stack[-1]]
			was_complete = self.choice_point_is_complete(c)
			released_atoms = c.reduce_solutions(stack[-1])
			t = tuple(c[:-1])
			for x in released_atoms:
				# how's this work for external specified root atoms?
				# could save 'em also; need a queue with faster then O(N) lookup for it though.
				self.deref_stack_for_atom(x, t)

			if c.no_solution:
				# notify the parents.
				# this work properly? :)
				istack.append(t)
			elif was_complete and not self.choice_point_is_complete(c):
				# if we've made it incomplete, well, time to go anew at it.
				self.stack.append(list(t))

		self.current_stack = self.stack[-1]

		if bail is not None:
			raise bail

	def choice_point_is_complete(self, choice_point):
		return all(x in self.atoms for x in chain(choice_point.depends, choice_point.rdepends))

	def ref_stack_for_atom(self, hashed_atom, stack):
		assert hashed_atom in self.atoms
		if not isinstance(stack, tuple):
			stack = tuple(stack)
		if stack not in self.atoms[hashed_atom][1]:
			self.atoms[hashed_atom][1].append(stack)

	def deref_stack_for_atom(self, hashed_atom, stack):
		assert hashed_atom in self.atoms
		if not isinstance(stack, tuple):
			stack = tuple(stack)
		l = [x for x in self.atoms[hashed_atom][1] if x != stack]
		if l:
			self.atoms[hashed_atom][1] = l
		else:
			del self.atoms[hashed_atom][1]
			

