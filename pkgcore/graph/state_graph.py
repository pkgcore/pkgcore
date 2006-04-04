# Copyright: 2005 Jason Stubbs <jstubbs@gentoo.org>
# Copyright: 2005-2006 Zac Medico <zmedico@gentoo.org>
# License: GPL2

from pkgcore.package.atom import atom
from pkgcore.restrictions.boolean import OrRestriction

# failings.  doesn't preserve ||() ordering/preference.
# this is because of unresolved_atoms being the method to get the unresolved atoms.


class StateGraph(object):

	# constants.  yes, bit unpythonic.
	pkg_combinations = 0
	pkg_atoms = 1
	pkg_satisfies_atoms = 2

	atom_parents = 0
	atom_matches = 1
	
	def __init__(self):
		# { pkg : ( [ combination ], Set( atom ), Set( matching atom ) ) }
		self.pkgs = {}
		# { atom : ( Set( parent package ), Set( matching package ) )
		self.atoms = {}
		self.dirty = False

	def add_pkg(self, pkg):
#		assert(pkg not in self.pkgs)
		if pkg in self.pkgs:
			return

		from pkgcore.restrictions import packages
		for x in pkg.rdepends.solutions():
			for node in x:
				if isinstance(node, packages.Conditional):
					import pdb;pdb.set_trace()
					

		self.dirty = True
		self.pkgs[pkg] = [map(frozenset, pkg.rdepends.solutions()), set(), set()]
		if len(self.pkgs[pkg][self.pkg_combinations]) <= 1:
			for atomset in self.pkgs[pkg][self.pkg_combinations]:
				self.pkgs[pkg][self.pkg_atoms].update(self.pkgs[pkg][self.pkg_atoms].union(atomset))
				self._add_pkg_atoms(pkg)

	def _add_pkg_atoms(self, pkg):
		for atom in self.pkgs[pkg][self.pkg_atoms]:
			if atom not in self.atoms:
				self.atoms[atom] = [set(), set()]
			self.atoms[atom][self.atom_parents].add(pkg)

	def _remove_pkg_atoms(self, pkg):
		for atom in self.pkgs[pkg][self.pkg_atoms]:
			self.atoms[atom][self.atom_parents].remove(pkg)
			if not self.atoms[atom][self.atom_parents]:
				for match in self.atoms[atom][self.atom_matches]:
					self.pkgs[match][self.pkg_satisfies_atoms].remove(atom)
				del self.atoms[atom]


	def calculate_deps(self):
		if not self.dirty:
			import traceback;traceback.print_stack()
			print "calcuate_deps called yet it wasn't dirty"
			return
		for atom in self.atoms:
			self.atoms[atom][self.atom_matches] = set()
		for pkg in self.pkgs:
			self.pkgs[pkg][self.pkg_satisfies_atoms] = set()
			if self.pkgs[pkg][self.pkg_atoms] and len(self.pkgs[pkg][self.pkg_combinations]) > 1:
				self._remove_pkg_atoms(pkg)
				self.pkgs[pkg][self.pkg_atoms] = set()
		for pkg in self.pkgs:
			if len(self.pkgs[pkg][self.pkg_combinations]) <= 1:
				continue
			all_atoms = set()
			for atomset in self.pkgs[pkg][self.pkg_combinations]:
				all_atoms.update(all_atoms.union(atomset))
			okay_atoms = set()

			# run blockers against all packages in the graph.
			# this should be just a subset, else it's O(N^2) for any calculation
			for atom in all_atoms:
				have_blocker=False
				for child in self.pkgs:
					if atom.key != child.key:
						continue
					if atom.match(child):
						if atom.blocks:
							have_blocker=True
						else:
							okay_atoms.add(atom)
						break

				if atom.blocks and not have_blocker:
					# blockers to ignore.
					okay_atoms.add(atom)

			# note entirely sure what this does.  selection strategy?
			differences={}
			for choice in self.pkgs[pkg][self.pkg_combinations]:
				difference = choice.difference(okay_atoms)
				if not difference:
					break
				differences[choice] = difference
			best_choice = choice
			if difference:
				for choice, difference in differences.iteritems():
					if len(difference) < len(differences[best_choice]):
						best_choice = choice
			self.pkgs[pkg][self.pkg_atoms].update(self.pkgs[pkg][self.pkg_atoms].union(best_choice))
			self._add_pkg_atoms(pkg)
		for pkg in self.pkgs:
			for atom in self.atoms:
				# XXX: Comparing keys is a hack to make things a little quicker
				# -- jstubbs
				if atom.key != pkg.key:
					continue
				if atom.match(pkg):
					self.pkgs[pkg][self.pkg_satisfies_atoms].add(atom)
					self.atoms[atom][self.atom_matches].add(pkg)
		for pkg in self.pkgs:
			if not pkg.metapkg:
				continue
			redirected_atoms = set()
			for parent_atom in self.pkgs[pkg][self.pkg_satisfies_atoms]:
				if not parent_atom.blocks:
					continue
				redirected_atoms.add(parent_atom)
				for parent_pkg in self.atoms[parent_atom][self.atom_parents]:
					for child_atom in self.pkgs[pkg][self.pkg_atoms]:
						if child_atom.blocks or child_atom.match(parent_pkg):
							continue
						for child_pkg in self.atoms[child_atom][self.atom_matches]:
							self.pkgs[child_pkg][self.pkg_satisfies_atoms].add(parent_atom)
							self.atoms[parent_atom][self.atom_matches].add(child_pkg)
			for atom in redirected_atoms:
				self.pkgs[pkg][self.pkg_satisfies_atoms].remove(atom)
				self.atoms[atom][self.atom_matches].remove(pkg)
		self.dirty = False

	def root_pkgs(self):
		if self.dirty:
			self.calculate_deps()
		return (pkg for pkg in self.pkgs if not self.pkgs[pkg][self.pkg_satisfies_atoms])

	def child_atoms(self, pkg):
		assert(pkg in self.pkgs)
		if self.dirty:
			self.calculate_deps()
		return self.pkgs[pkg][self.pkg_atoms]

	def child_pkgs(self, atom):
		assert(atom in self.atoms)
		if self.dirty:
			self.calculate_deps()
		return self.atoms[atom][self.atom_matches]

	def parent_atoms(self, pkg):
		assert(pkg in self.pkgs)
		if self.dirty:
			self.calculate_deps()
		return self.pkgs[pkg][self.pkg_satisfies_atoms]

	def parent_pkgs(self, atom):
		assert(atom in self.atoms)
		if self.dirty:
			self.calculate_deps()
		return self.atoms[atom][self.atom_parents]

	def unresolved_atoms(self):
		if self.dirty:
			self.calculate_deps()
		return (atom for atom, data in self.atoms.iteritems() if not atom.blocks and not data[self.atom_matches])

	def resolved_atoms(self):
		if self.dirty:
			self.calculate_deps()
		return (atom for atom, data in self.atoms.iteritems() if not atom.blocks and data[self.atom_matches])

	def blocking_atoms(self):
		if self.dirty:
			self.calculate_deps()
		return (atom for atom, data in self.atoms.iteritems() if atom.blocks and data[self.atom_matches])


# kind of a screwed up intersect
def extrapolate(set1, set2):

	final_set = set1.intersection(set2)

	set1 = set1.difference(final_set)
	set2 = set2.difference(final_set)

	combs = []
	for subset1 in set1:
		for subset2 in set2:
			combs.append(subset1.union(subset2))

	for subset1 in combs:
		required = True
		removable = set()
		for subset2 in final_set:
			if subset1.issuperset(subset2):
				required = False
				break
			elif subset1.issubset(subset2):
				removable.add(subset2)
		for subset2 in removable:
			final_set.remove(subset2)
		if required:
			final_set.add(subset1)

	return final_set


