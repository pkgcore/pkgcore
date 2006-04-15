# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.lists import stable_unique
from pkgcore.graph.util import atom_queue

class solution_space(object):
	def __init__(self, pkg, solutions):
		assert solutions
		self.pkg, self.solutions = pkg, solutions
		self.solution_index = -1
		self._common_atoms = None

	@property
	def processing_commons(self):
		return self.solution_index == -1
	
	@property
	def common_atoms(self):
		if self._common_atoms is None:
			if len(self.solutions) == 1:
				common = tuple(self.solutions[0])
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
	def current_solution(self):
		assert self._common_atoms is not None
		assert self.solution_index >= 0
		return self.solutions[self.solution_index]
	
	@property
	def next_solution(self):
		# folks should have the calling order right.
		assert self._common_atoms is not None
		try:
			self.solution_index = self.solution_index + 1
			s = self.solutions[self.solution_index]
		except IndexError:
			return None
		return s
	
	def reset_solutions(self):
		self.solution_index = 0
	
	def __str__(self):
		return "pkg(%s): %s" % (self.pkg, str(self.solutions))


class choice_point(object):
	
	def __init__(self, a, matches):
		self.atom = a
		self.matches = matches
		self.position = -1
	
	@property
	def next_choice(self):
		self.position += 1
		try:
			return self.matches[self.position]
		except IndexError:
			return None
	
	@property
	def current_choice(self):
		if self.position < 0:
			raise Exception("position was -1, call order was wrong")
		return self.matches[self.position]
		
	

class resolver(object):
	def __init__(self):
		# choicepoint, processing common?, pos
		self.stack = []
		self.added_atoms_stack = []
		self.fast_stack = set()
		self.atoms = {}
		self.pkgs = {}
	
	def iterate_unresolved_atoms(self):
		while self.stack:
			s = self.stack[-1]
			if isinstance(s, choice_point):
				# grab the next (potentially first) solution.
				c = s.next_choice
				if c is not None:
					self.append_choice_point_solutions(c)
					continue
			elif isinstance(s, solution_space):
				if s.processing_commons:
					# proved the commons atoms for this solution.
					self.stack.extend(s.common_atoms)
					self.added_atoms_stack.append([])
				else:
					# proved this solution.
					self.added_atoms_stack.pop(-1)
					continue
			else:
				# an atom.
				yield s
	
	def satisfy_atom(self, a, matches):
		assert a is self.stack[-1]
		self.stack.pop(-1)
		c = choice_point(a, matches)
		self.stack.append(c)
		self.added_atoms_stack.append(a)

	def append_choice_point_solutions(self, pkg):
		s2 = pkg.rdepends.solutions()
		if s2:
			self.stack.append(solution_space(pkg, s2))
		s2 = pkg.depends.solutions()
		if s2:
			self.stack.append(solution_space(pkg, s2))
		if isinstance(self.stack[-1], choice_point):
			# huh.  virtual node maybe.
			# well, this node is proven.
			self.stack.pop(-1)
		
	def unsatisfiable_atom(self, atom):
		assert atom is self.stack[-1]
		# joy oh joys.
		while self.stack:
			if isinstance(s, solution_space):
				atoms_added = set(self.added_atoms_stack.pop(-1))
				n = s.next_solution
				kills = atoms_added
				saves = None
				if s.processing_commons or n is None:
					kills = True
				else:
					ns = set(n)
					kills = atoms_added.difference(ns)
					saves = atoms.added.intersection(ns)

				if kills is True:
					# non usable or exhausted solution space.
					while isinstance(self.stack[-1], solution_space):
						self.stack.pop(-1)
				else:
					for x in kills:
						del self.atoms[x]
					self.added_atoms_stack.append(list(saves))
					self.stack.extend(x for x in n if x not in saves)
					return
			
			elif isinstance(s, choice_point):
				c = s.next_choice
				if n is None:
					# old gal has no more in her.
					self.stack.pop(-1)
					continue
				self.append_choice_point_solutions(c)
				return
			else:
				self.stack.pop(-1)
					

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

