import itertools
from pkgcore.util.compatibility import any, all
from pkgcore.util.iterables import caching_iter
from pkgcore.graph.pigeonholes import PigeonHoledSlots
from pkgcore.graph.resolver import resolver
from pkgcore.package.atom import atom
from pkgcore.util.currying import pre_curry

INSTALL = 1
REMOVE = 0
PREEXISTING = 2

class entry(object):
	def __init__(self, atom, pkg, entry_type):
		self.type = entry_Type
		self.deps = []
		self.revdeps = set()
		self.atom = atom
		self.pkg = pkg

	def register_parent(self, entry):
		self.revdeps.add(entry)
	
	def deregister_parent(self, entry):
		self.revdeps.discard(entry)
	
	def __nonzero__(self):
		return bool(self.revdeps)


class entrylist(list):
	pass


class merge_plan(object):
	
	def __init__(self, vdb, dbs, pkg_selection_strategy=None, load_initial_vdb_state=True):
		if pkg_selection_strategy is None:
			pkg_selection_strategy = self.reuse_strategy
		if not isinstance(dbs, (list, tuple)):
			dbs = [dbs]
		self.db, self.vdb = dbs, vdb
		self.cached_queries = {}
		self.buildplan = entrylist()
		self.forced_atoms = set()
		self.resolver = resolver()
		#should probably proxy self to avoid cycles...
		self.get_matches = pre_curry(self, pkg_selection_strategy)
		self.tail_state = PigeonHoledSlots()
		self.load_vdb_blockers = load_initial_vdb_state

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
			self.forced_atoms.add(atom)
			self.resolver.add_root_atom(atom)

	def iterate_unresolved_atoms(self):
		return self.resolver.iterate_unresolved_atoms()

	def satisfy_atom(self, *a):
		return self.resolver.satisfy_atom(*a)

	def linearize(self, plan=None):
		state = PigeonHoledSlots()
		

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
