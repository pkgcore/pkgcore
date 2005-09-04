
from portage.package.atom import atom
from portage.restrictions.packages import OrRestriction

class StateGraph(object):

	def __init__(self):
		# { pkg : [combinations], [chosen combination], [ matching atom ] }
		self.pkgs = {}
		# { atom : [ [ parent package ], [ matching package ] }
		self.atoms = {}
		self.dirty = False

	def add_pkg(self, pkg):
		assert(pkg not in self.pkgs)
		self.dirty = True
		if pkg.package == "xterm":
			print pkg.rdepends
		self.pkgs[pkg] = [combinations(pkg.rdepends), None, []]
		for combination in self.pkgs[pkg][0]:
			self._add_deps(pkg, combination)
		if len(self.pkgs[pkg][0]) == 1:
			self.pkgs[pkg][1] = self.pkgs[pkg][0][0]

	def _add_deps(self, pkg, combination):
		for atom in combination:
			if atom in self.atoms:
				self.atoms[atom][0].append(pkg)
			else:
				self.atoms[atom] = [[pkg], []]

	def _remove_deps(self, pkg, combination):
		for atom in combination:
			self.atoms[atom][0].remove(pkg)
			if not self.atoms[atom][0]:
				for match in self.atoms[atom][1]:
					self.pkgs[match][2].remove(atom)
				del self.atoms[atom]

	def calculate_deps(self):
		if not self.dirty:
			return
		for atom in self.atoms:
			self.atoms[atom][1] = []
		for pkg in self.pkgs:
			self.pkgs[pkg][2] = []
			if self.pkgs[pkg][1] is not None and len(self.pkgs[pkg][0]) != 1:
				self._remove_deps(pkg, self.pkgs[pkg][1])
				self.pkgs[pkg][1] = None
				for combination in self.pkgs[pkg][0]:
					self._add_deps(pkg, combination)
		multicomb = []
		for pkg in self.pkgs:
			if len(self.pkgs[pkg][0]) != 1:
				multicomb.append(pkg)
				continue
			if self.pkgs[pkg][1] is not None:
				continue
			self.pkgs[pkg][1] = self.pkgs[pkg][0][0]
		for pkg in multicomb:
			unsatisfied_counts = {}
			for combination in self.pkgs[pkg][0]:
				count = 0
				for atom in combination:
					satisfied = False
					for p in self.pkgs:
						if p.key != atom.key:
							continue
						if atom.match(p):
							satisfied = True
							break
					if not satisfied:
						count += 1
				if not count:
					unsatisfied_counts = {0:[combination]}
					break
				if count not in unsatisfied_counts:
					unsatisfied_counts[count] = [combination]
				else:
					unsatisfied_counts[count]+= [combination]
			counts = unsatisfied_counts.keys()
			counts.sort()
			combination = unsatisfied_counts[counts[0]][0]
			self.pkgs[pkg][1] = combination
			self._add_deps(pkg, combination)
			for combination in self.pkgs[pkg][0]:
				self._remove_deps(pkg, combination)
		for pkg in self.pkgs:
			for atom in self.atoms:
				# XXX: Comparing keys is a hack to make things a little quicker
				# -- jstubbs
				if atom.key != pkg.key:
					continue
				if atom.match(pkg):
					self.pkgs[pkg][2].append(atom)
					self.atoms[atom][1].append(pkg)
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


def combinations(restrict):
	ret = []

	if isinstance(restrict, OrRestriction):
		# XXX: OrRestrictions currently contain a single DepSet that contains
		# the Or'd elements. This seems broken to me.
		# -- jstubbs
		for element in restrict[0]:
			if isinstance(element, atom):
				ret += [[element]]
			else:
				ret += combinations(element)
	else:
		singles = []
		others = []
		seen = []
		for element in restrict:
			if hash(element) in seen:
				continue
			seen.append(hash(element))
			if isinstance(element, atom):
				singles += [element]
			else:
				others += [combinations(element)]
		if others:
			indexes = []
			endindex = len(others)
			for x in range(endindex):
				indexes.append(0)
			index = 0
			while index != endindex:
				if indexes[index] >= len(others[index]):
					index += 1
					if index == endindex:
						continue
					for x in range(index):
						indexes[x] = 0
					indexes[index] += 1
					continue
				else:
					index = 0
				newcomb = singles[:]
				for x in range(endindex):
					if others[x]:
						newcomb.extend(others[x][indexes[x]])
				ret.append(newcomb)
				indexes[index] += 1
		else:
			ret = [singles]
	return ret
