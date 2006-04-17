from pkgcore.restrictions import packages, values
from pkgcore.util.iterables import expandable_chain, caching_iter
from pkgcore.util.compatibility import all
from pkgcore.graph.choice_point import choice_point


debug_whitelist = [None]
def debug(msg, id=None):
	if id in debug_whitelist:
		print "debug: %s" % msg


class NoSolution(Exception):
	def __init__(self, msg):
		self.msg = msg
	def __str__(self):
		return str(msg)


class resolver(object):

	def __init__(self):
		self.search_stacks = [[]]
		self.grab_next_stack()
		self.current_atom = None
		self.false_atoms = set()
		self.atoms = {}

	def add_root_atom(self, atom):
		if atom in self.atoms:
			# register a root level stack
			self.ref_stack_for_atom(h, [])
		else:
			self.search_stacks.append([atom])
			self.grab_next_stack()

	def grab_next_stack(self):
		self.current_stack = self.search_stacks[-1]

	def iterate_unresolved_atoms(self):
		while self.search_stacks:
			assert self.current_stack is self.search_stacks[-1]
			if not self.current_stack:
				self.search_stacks.pop(-1)
				if not self.search_stacks:
					self.current_stack = None
					return
				self.grab_next_stack()
				continue

			debug("stack is %s" % self.current_stack)
			a = self.current_stack[-1]
			if a not in self.atoms:
				debug("  missing atom: %s" % a)
				yield a
				continue
			
			c = self.atoms[a][0]
			t = tuple(self.current_stack)
			missing_atoms = False
			for x in c.depends + c.rdepends:
				# yes this is innefficient
				if x not in self.atoms:
					self.current_stack.append(x)
					missing_atoms = True
					break
				else:
					#ensure we're registered.
					self.ref_stack_for_atom(x, t)
		
			if missing_atoms:
				debug("  missing_atoms for %s: %s" % (a, self.current_stack[-1]))
				# cycle protection.
				self.current_atom = self.current_stack[-1]
				
				if self.current_atom == a:
					# cycle ask the repo for a pkg configuration that breaks the cycle.
					import pdb;pdb.set_trace()
					v = values.ContainmentMatch(a, negate=True)
					yield packages.AndRestriction(self.current_atom, 
						PackageRestriction("depends", v), PackageRestriction("rdepends", v))
				else:
					yield self.current_atom
			else:
				# all satisfied.
				self.current_stack.pop(-1)
	
	def satisfy_atom(self, atom, matches):
		assert atom is self.current_stack[-1]
		c = choice_point(atom, caching_iter(matches))
		if not c:
			self.unsatisfiable_atom(atom)
			return

		self.atoms[atom] = [c, []]
		# is this right?
		self.ref_stack_for_atom(atom, self.current_stack)
		print "left it",self.search_stacks
		print "atoms",self.atoms
		
	def unsatisfiable_atom(self, atom, msg="None supplied"):
		# what's on the stack may be different from current_atom; union of atoms will do this fex.
		assert atom is self.current_atom

		a = self.current_atom

		# register this as unsolvable
		self.false_atoms.add(atom)

		bail = None
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
				if c.package == "libc":
					import pdb;pdb.set_trace()
				istack.append(t)
			elif was_complete and not self.choice_point_is_complete(c):
				# if we've made it incomplete, well, time to go anew at it.
				self.stack.append(list(t))

		self.current_stack = self.stack[-1]

		if bail is not None:
			raise bail

	def choice_point_is_complete(self, choice_point):
		return all(x in self.atoms for x in choice_point.depends) and \
			all(x in self.atoms for x in choice_point.rdepends)

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
			
