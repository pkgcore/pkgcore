# Copyright: 2005 Gentoo Foundation
# Author(s): Jason Stubbs (jstubbs@gentoo.org)
# License: GPL2
# $Id:$


import sets

from portage.package.atom import atom
from portage.restrictions.packages import OrRestriction

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
		self.pkgs[pkg] = (combinations(pkg.rdepends), sets.Set(), sets.Set())
		if len(self.pkgs[pkg][0]) <= 1:
			for atomset in self.pkgs[pkg][0]:
				self.pkgs[pkg][1].union_update(atomset)
				self._add_deps(pkg)

	def _add_deps(self, pkg):
		for atom in self.pkgs[pkg][1]:
			if atom not in self.atoms:
				self.atoms[atom] = [sets.Set(), sets.Set()]
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
			all_atoms = sets.Set()
			for atomset in self.pkgs[pkg][0]:
				all_atoms.union_update(atomset)
			okay_atoms = sets.Set()
			for atom in all_atoms:
				for child in self.pkgs:
					if atom.key != child.key:
						continue
					if atom.match(child) ^ atom.blocks:
						okay_atoms.add(atom)
						break
			for choice in self.pkgs[pkg][0]:
				if choice.issubset(okay_atoms):
					break
			# XXX: A random set will be chosen if there are no fully matching sets
			# -- jstubbs
			self.pkgs[pkg][1].union_update(choice)
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
			redirected_atoms = sets.Set()
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
		removable = sets.Set()
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


def combinations(restrict):
	ret = sets.Set()

	if isinstance(restrict, OrRestriction):
		# XXX: OrRestrictions currently contain a single DepSet that contains
		# the Or'd elements. This seems broken to me.
		# -- jstubbs
		for element in restrict[0]:
			if isinstance(element, atom):
				newset = sets.Set()
				newset.add(element)
				ret.add(newset)
			else:
				ret = extrapolate(ret, combinations(element))
	else:
		newset = sets.Set()
		subsets = sets.Set()
		for element in restrict:
			if isinstance(element, atom):
				newset.add(element)
			else:
				subsets.add(combinations(element))
		ret.add(newset)
		for comb in subsets:
			ret = extrapolate(ret, comb)

	return ret
