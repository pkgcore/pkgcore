import itertools
from collections import deque
from pkgcore.util.compatibility import any, all
from pkgcore.util.iterables import caching_iter
from pkgcore.graph.pigeonholes import PigeonHoledSlots
from pkgcore.graph.choice_point import choice_point
from pkgcore.util.currying import pre_curry
from pkgcore.restrictions import packages, values, boolean

REMOVE  = 0
ADD     = 1
REPLACE = 2
FORWARD_BLOCK = 3

class nodeps_repo(object):
	def __init__(self, repo):
		self.__repo = repo
	def itermatch(self, *a, **kwds):
		return (nodeps_pkg(x) for x in self.__repo.itermatch(*a, **kwds))
	
	def match(self, *a, **kwds):
		return list(self.itermatch(*a, **kwds))


class nodeps_pkg(object):
	def __init__(self, pkg):
		self._pkg = pkg
	def __getattr__(self, attr):
		if attr in ("depends", "rdepends"):
			return packages.AndRestriction(finalize=True)
		return getattr(self._pkg, attr)

	def __cmp__(self, other):
		if isinstance(other, self.__class__):
			return cmp(self._pkg, other._pkg)
		return cmp(self._pkg, other)

class InconsistantState(Exception):
	pass


class InsolubleSolution(Exception):
	pass


class merge_plan(object):
	
	def __init__(self, vdb, dbs, pkg_selection_strategy=None, load_initial_vdb_state=True, verify_vdb=False):
		if pkg_selection_strategy is None:
			pkg_selection_strategy = self.prefer_highest_version_strategy
		if not isinstance(dbs, (list, tuple)):
			dbs = [dbs]
		self.db, self.vdb = dbs, vdb
		self.cached_queries = {}
		self.forced_atoms = set()

		self.pkg_selection_strategy = pkg_selection_strategy
		self.verify_vdb_deps = verify_vdb
		if not verify_vdb:
			self.vdb = nodeps_repo(vdb)
		self.state = plan_state()
		self.load_vdb_blockers = load_initial_vdb_state
		self.insoluble = set()
		self.atom_cache = {}

	def _load_vdb_blockers(self):
		raise Exception("non working, piss off you wanker")
		print "(re)loading vdb rdepends blockers..."
		for pkg in self.vdb:
			#solve this by plucking the actual solution on disk via solutions.
			blockers = [a for a in pkg.rdepends if isinstance(a, atom) and a.blocks]
			if blockers:
				l = self.state.match_atom(pkg)
				if l:
					raise Exception("vdb pkg %s consumes same slot as/is blocked by %s" % (pkg, l))
				for b in blockers:
					l = self.state.add_blocker(b)
					if l:
						raise Exception("vdb pkg %s levels blocker %s, which blocks %s- vdb is inconsistant" % (pkg, b, ke))
			
		print "finished"
	
	def add_atom(self, atom):
		if atom not in self.forced_atoms:
			stack = deque()
			self._rec_add_atom(atom, stack)
			ret = self.forced_atoms.add(atom)
			if ret:
				print "failed- %s" % ret
				import pdb;pdb.set_trace()
				return False
		return True

	def _rec_add_atom(self, atom, current_stack):
		"""returns false on no issues (inserted succesfully), else a list of the stack that screwed it up"""
		if atom in self.insoluble:
			return [atom]
		l = self.state.match_atom(atom)
		if l:
			return False
		# not in the plan thus far.
		matches = self.get_db_matches(atom)
		if matches:
			choices = choice_point(atom, self.get_db_matches(atom))
			# ignore what dropped out, at this juncture we don't care.
			choices.reduce_atoms(self.insoluble)
			if not choices:
				matches = None
				# and was intractable because it has a hard dep on an unsolvable atom.
		if not matches:
			self.insoluble.add(atom)
			return [atom]

		current_stack.append(atom)

		blocks = []
		print "processing      ",atom
		while choices:
			satisfied = True
			additions, blocks, nolonger_used = [], [], []
			for datom in choices.depends:
				if datom.blocks:
					# don't register, just do a scan.  and this sucks because any later insertions prior to this won't get
					# hit by the blocker
					l = self.state.match_atom(datom)
					if l:
						print "depends blocker messing with us- dumping to pdb for inspection"
						import pdb;pdb.set_trace()
						raise Exception("whee, damn depends blockers")
				else:
					if datom in current_stack:
						# cycle.
#						new_atom = packages.AndRestriction(datom, packages.Restriction("depends", 
#							values.ContainmentMatch(datom, 
						import pdb;pdb.set_trace()
					failure = self._rec_add_atom(datom, current_stack)
					if failure:
						# reduce.
						nolonger_used = choices.reduce_atoms(datom)
						satisfied = False
						break
					additions.append(datom)
			if satisfied:
				for ratom in choices.rdepends:
					if ratom in current_stack:
						# cycle.  whee.
						pass
					if ratom.blocks:
						# level blockers after resolution of this node- blocker may block something that is required 
						# only as depends for a node required for rdepends
						blocks.append(ratom)
					else:
						failure = self._rec_add_atom(ratom, current_stack)
						if failure:
							# reduce.
							nolonger_used = choices.reduce(ratom)
							satisfied = False
							break
					additions.append(ratom)

			if not satisfied:
				# need to clean up blockers here... cleanup our additions in light of reductions from choices.reduce
				print "dirty dirty little boy!  skipping cleaning"
			else:
				break

		if not choices:
			print "found no solution for %s" % atom
			current_stack.pop()
			return [atom] + failure

		# well, we got ourselvs a resolution.
		l = self.state.add_pkg(choices)
		if l:
			# this means in this branch of resolution, someone slipped something in already.
			# cycle, basically.
			print "was trying to insert atom %s pkg %s, but %s exists already" (atom, choices.current_pkg, l)
			import pdb;pdb.set_trace()
		# level blockers.
		for x in blocks:
			l = self.state.add_blocker(x)
			if l:
				# blocker caught something. yay.
				print "rdepend blocker %x hit %s for atom %s pkg %s" % (x, l, atom, choices_current.pkg)
				import pdb;pdb.set_trace()
		current_stack.pop()
		return False
	
	def get_db_matches(self, atom):
		print "querying db for ",atom
		if atom in self.insoluble:
			return []
		matches = self.atom_cache.get(atom, None)
		if matches is None:
			matches = self.pkg_selection_strategy(self, atom)
			if not isinstance(matches, caching_iter):
				matches = caching_iter(matches)
			self.atom_cache[atom] = matches
		return matches

	# selection strategies for atom matches
	@staticmethod
	def prefer_highest_version_strategy(self, atom):
		return caching_iter(itertools.chain(*[r.itermatch(atom) for r in self.db + [self.vdb]]), sorted)

	@staticmethod
	def prefer_reuse_strategy(self, atom):
		return caching_iter(itertools.chain(
			self.vdb.itermatch(atom), 
			caching_iter(itertools.chain(*[r.itermatch(atom) for r in self.db]), sorted)
		))

	@staticmethod
	def force_max_strategy(self, atom):
		try:
			yield max(self.vdb.match(atom) + [pkg for repo in self.db for pkg in db.itermatch(atom)])
		except ValueError:
			# max throws it if max([]) is called.
			yield []

	@staticmethod
	def force_min_strategy(self, atom):
		try:
			yield min(self.vdb.match(atom) + [pkg for repo in self.db for pkg in db.itermatch(atom)])
		except ValueError:
			# max throws it if max([]) is called.
			yield []


class plan_state(object):
	def __init__(self):
		self.state = PigeonHoledSlots()
		self.plan = []
	
	def add_pkg(self, choices, action=ADD):
		"""returns False (no issues), else the conflicts"""
		if action == REMOVE:
			# level it even if it's not existant?
			self.state.remove_slotting(choices.current_pkg)
			self.plan.append((action, choices))
		elif action == ADD:
			l = self.state.fill_slotting(choices.current_pkg)
			if l:
				return l
			self.plan.append((action, choices))
		return False
		
	def add_blocker(self, blocker):
		"""adds blocker, returning any packages blocked"""
		l = self.state.add_limiter(blocker)
		self.plan.append((FORWARD_BLOCK, blocker))
		return l

	def match_atom(self, atom):
		return self.state.find_atom_matches(atom)
