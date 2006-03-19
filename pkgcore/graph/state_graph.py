# Copyright: 2005 Jason Stubbs <jstubbs@gentoo.org>
# Copyright: 2005-2006 Zac Medico <zmedico@gentoo.org>
# License: GPL2

from pkgcore.package.atom import atom
from pkgcore.restrictions.boolean import OrRestriction

class StateGraph(object):

	def __init__(self):
		# { pkg : ( [ combination ], Set( atom ), Set( matching atom ) ) }
		self.pkgs = {}
		# { atom : ( Set( parent package ), Set( matching package ) )
		self.atoms = {}
		self.dirty = False

	def add_pkg(self, pkg):
		assert(pkg not in self.pkgs)
		self.dirty = True
		self.pkgs[pkg] = (combinations(pkg.rdepends, atom), set(), set())
		if len(self.pkgs[pkg][0]) <= 1:
			for atomset in self.pkgs[pkg][0]:
				self.pkgs[pkg][1].update(self.pkgs[pkg][1].union(atomset))
				self._add_deps(pkg)

	def _add_deps(self, pkg):
		for atom in self.pkgs[pkg][1]:
			if atom not in self.atoms:
				self.atoms[atom] = [set(), set()]
			self.atoms[atom][0].add(pkg)

	def _remove_deps(self, pkg):
		for atom in self.pkgs[pkg][1]:
			self.atoms[atom][0].remove(pkg)
			if not self.atoms[atom][0]:
				for match in self.atoms[atom][1]:
					self.pkgs[match][2].remove(atom)
				del self.atoms[atom]

	def calculate_deps(self):
		if not self.dirty:
			return
		for atom in self.atoms:
			self.atoms[atom][1].clear()
		for pkg in self.pkgs:
			self.pkgs[pkg][2].clear()
			if self.pkgs[pkg][1] and len(self.pkgs[pkg][0]) > 1:
				self._remove_deps(pkg)
				self.pkgs[pkg][1].clear()
		for pkg in self.pkgs:
			if len(self.pkgs[pkg][0]) <= 1:
				continue
			all_atoms = set()
			for atomset in self.pkgs[pkg][0]:
				all_atoms.update(all_atoms.union(atomset))
			okay_atoms = set()
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
					# block atom that does not match any packages
					okay_atoms.add(atom)
			differences={}
			for choice in self.pkgs[pkg][0]:
				difference = choice.difference(okay_atoms)
				if not difference:
					break
				differences[choice] = difference
			best_choice = choice
			if difference:
				for choice, difference in differences.iteritems():
					if len(difference) < len(differences[best_choice]):
						best_choice = choice
			self.pkgs[pkg][1].update(self.pkgs[pkg][1].union(best_choice))
			self._add_deps(pkg)
		for pkg in self.pkgs:
			for atom in self.atoms:
				# XXX: Comparing keys is a hack to make things a little quicker
				# -- jstubbs
				if atom.key != pkg.key:
					continue
				if atom.match(pkg):
					self.pkgs[pkg][2].add(atom)
					self.atoms[atom][1].add(pkg)
		for pkg in self.pkgs:
			if not pkg.metapkg:
				continue
			redirected_atoms = set()
			for parent_atom in self.pkgs[pkg][2]:
				if not parent_atom.blocks:
					continue
				redirected_atoms.add(parent_atom)
				for parent_pkg in self.atoms[parent_atom][0]:
					for child_atom in self.pkgs[pkg][1]:
						if child_atom.blocks or child_atom.match(parent_pkg):
							continue
						for child_pkg in self.atoms[child_atom][1]:
							self.pkgs[child_pkg][2].add(parent_atom)
							self.atoms[parent_atom][1].add(child_pkg)
			for atom in redirected_atoms:
				self.pkgs[pkg][2].remove(atom)
				self.atoms[atom][1].remove(pkg)
		self.dirty = False

	def root_pkgs(self):
		if self.dirty:
			self.calculate_deps()
		for pkg in self.pkgs:
			if not self.pkgs[pkg][2]:
				yield pkg

	def child_atoms(self, pkg):
		assert(pkg in self.pkgs)
		if self.dirty:
			self.calculate_deps()
		for atom in self.pkgs[pkg][1]:
			yield atom

	def child_pkgs(self, atom):
		assert(atom in self.atoms)
		if self.dirty:
			self.calculate_deps()
		for pkg in self.atoms[atom][1]:
			yield pkg

	def parent_atoms(self, pkg):
		assert(pkg in self.pkgs)
		if self.dirty:
			self.calculate_deps()
		for atom in self.pkgs[pkg][2]:
			yield atom

	def parent_pkgs(self, atom):
		assert(atom in self.atoms)
		if self.dirty:
			self.calculate_deps()
		for parent in self.atoms[atom][0]:
			yield parent

	def unresolved_atoms(self):
		if self.dirty:
			self.calculate_deps()
		for atom in self.atoms:
			if atom.blocks:
				continue
			if not self.atoms[atom][1]:
				yield atom

	def blocking_atoms(self):
		if self.dirty:
			self.calculate_deps()
		for atom in self.atoms:
			if not atom.blocks:
				continue
			if self.atoms[atom][1]:
				yield atom


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


def combinations(restrict, elem_type=atom):
	ret = set()

	if isinstance(restrict, OrRestriction):
		for element in restrict:
			if isinstance(element, elem_type):
				newset = set()
				newset.add(element)
				ret.add(frozenset(newset))
			else:
				ret.update(ret.union(combinations(element, elem_type)))
	else:
		newset = set()
		subsets = set()
		for element in restrict:
			if isinstance(element, elem_type):
				newset.add(element)
			else:
				subsets.add(frozenset(combinations(element, elem_type)))
		ret.add(frozenset(newset))
		for comb in subsets:
			ret = extrapolate(ret, comb)

	return ret
