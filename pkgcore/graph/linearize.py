import itertools
from collections import dequeue
from pkgcore.util.compatibility import any, all
from pkgcore.util.iterables import caching_iter
from pkgcore.graph.pigeonholes import PigeonHoledSlots
from pkgcore.graph.choice_point import choice_point
from pkgcore.package.atom import atom
from pkgcore.util.currying import pre_curry

MERGED  = 0
MERGE   = 1
UNMERGE = 2
REPLACE = 3

class entry(object):
	def __init__(self, atom, data, entry_type, preblocks):
		self.type = entry_Type
		self.deps = []
		self.revdeps = set()
		self.atom = atom
		self.pkg = data
		self.preblocks = preblocks

	def register_parent(self, entry):
		self.revdeps.add(entry)
	
	def deregister_parent(self, entry):
		self.revdeps.discard(entry)
	
	def __nonzero__(self):
		return bool(self.revdeps)


class InconsistantState(Exception):
	pass


class InsolubleSolution(Exception):
	pass


class entrylist(list):
	def generate_state(self):
		state = PigeonHoledSlots()
		for idx, step in enumerate(self):
			if step.type in (MERGED, MERGE):
				l = state.fill_slotting(step.data.pkg)
			elif step.type == UNMERGE:
				# sanity check.  ensure what we're unmerging is in the graph.
				assert step.data.pkg in state
				state.remove_slotting(step.data.pkg)
				assert step.data.pkg not in state
				l = None
			elif step.type == REPLACE:
				# assert the target is in the state
				assert step.data[0] in state
				assert step.data[1] not in state
				state.remove_slotting(step.data[0])
				l = state.fill_slotting(step.data[1])
			else:
				raise AssertionError("step %s idx %d is of unknown type" % (step, idx))
			if l:
				raise InconsistantState("entry %s, idx %d conflicts with state %s" % (step, idx, l))
		return state


class merge_plan(object):
	
	def __init__(self, vdb, dbs, pkg_selection_strategy=None, load_initial_vdb_state=True):
		if pkg_selection_strategy is None:
			pkg_selection_strategy = self.reuse_strategy
		if not isinstance(dbs, (list, tuple)):
			dbs = [dbs]
		self.db, self.vdb = dbs, vdb
		self.cached_queries = {}
		self.plan = entrylist()
		self.forced_atoms = set()

		self.pkg_selection_strategy = pkg_selection_strategy
		self.tail_state = PigeonHoledSlots()
		self.load_vdb_blockers = load_initial_vdb_state
		self.insoluble = set()
		self.atom_cache = {}

	def _load_vdb_blockers(self):
		print "(re)loading vdb rdepends blockers..."
		for pkg in self.vdb:
			blockers = [a for a in pkg.rdepends if isinstance(a, atom) and a.blocks]
			if blockers:
				l = self.tail_state.fill_slotting(pkg)
				if l:
					raise Exception("vdb pkg %s consumes same slot as/is blocked by %s" % (pkg, l))
				for b in blockers:
					l = self.tail_state.add_limiter(b)
					if l:
						raise Exception("vdb pkg %s levels blocker %s, which blocks %s- vdb is inconsistant" % (pkg, b, ke))
			
		print "finished"
	
	def add_atom(self, atom):
		if atom not in self.forced_atoms:
			self._rec_add_atom(atom)
			ret = self.forced_atoms.add(atom)
			if ret is not True:
				self.regen_state()
			
	def _rec_add_atom(self, atom):
		"""returns false on no issues (inserted succesfully), else a list of the stack that screwed it up"""
		if atom in self.insoluble:
			return [atom]
		l = self.tail_state.find_atom_matches(atom)
		if l:
			return False
		# not in the plan thus far.
		
		choices = choice_point(atom, self.get_db_matches(atom))
		# ignore what dropped out, at this juncture we don't care.
		choices.reduce_atoms(self.insoluble)
		if not choices:
			# and was intractable because it has a hard dep on an unsolvable atom.
			self.insoluble.add(atom)
			return [atom]

		satisfied = True
		blocks = []
		while choices:
			satisfied=True
			additions, blocks, nolonger_used = [], [], []
			for datom in choices.pkg.depends:
				if datom.blocks:
					# don't register, just do a scan.  and this sucks because any insertions prior to this won't get
					# hit by the blocker
					l = self.tail_state.find_atom_matches(datom)
					if l:
						print "depends blocker messing with us- dumping to pdb for inspection"
						import pdb;pdb.set_trace()
						raise Exception("whee, damn depends blockers")
				else:
					ret = self._rec_add_atom(datom)
					if ret:
						# reduce.
						nolonger_used = choices.reduce(datom)
						satisfied = False
						break
					additions.append(datom)
			if satisfied:
				for ratom in choices.pkg.rdepends:
					if ratom.blocks:
						# level blockers after resolution of this node- blocker may block something that is required 
						# only as depends for a node required for rdepends
						blocks.append(ratom)
					else:
						ret = self._rec_add_atom(ratom)
						if ret:
							# reduce.
							nolonger_used = choices.reduce(ratom)
							satisfied = False
							break
					additions.append(ratom)

			if not satisified:
				# need to clean up blockers here... cleanup our additions in light of reductions from choices.reduce
				print "dirty dirty little boy!  skipping cleaning"
			else:
				break
		if choices:
			# well, we got ourselvs a resolution.
			self.plan.append(choices)
			# level blockers.
			live_blocks = {}
			
			
	def regen_state(self):
		# brute force.
		self.tail_state = self.plan.generate_state()	

	def get_db_matches(self, atom):
		if atom in self.insoluble:
			return []
		matches = self.atom_cache.get(atom, None):
		if matches is None:
			matches = self.pkg_selection_strategy(self, atom)
			if not isinstance(matches, caching_iter):
				matches = caching_iter(matches)
			self.atom_cache[atom] = matches
		return matches

	# selection strategies for atom matches
	@staticmethod
	def highest_version_strategy(self, atom):
		return caching_iter(itertools.chain(*[r.itermatch(atom) for r in self.db + self.vdb]), sorted)

	@staticmethod
	def reuse_strategy(self, atom):
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
