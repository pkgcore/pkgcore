
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
		self.pkgs[pkg] = [combinations(pkg.rdepends), None, []]
		if self.pkgs[pkg][0][1] <= 1:
			self.pkgs[pkg][1] = self.pkgs[pkg][0][0].keys()
			self._add_deps(pkg, self.pkgs[pkg][1])

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
			if self.pkgs[pkg][1] is not None and self.pkgs[pkg][0][1] > 1:
				self._remove_deps(pkg, self.pkgs[pkg][1])
				self.pkgs[pkg][1] = None
		for pkg in self.pkgs:
			if self.pkgs[pkg][0][1] <= 1:
				continue
			indices = {}
			for index in range(self.pkgs[pkg][0][1]):
				indices[index] = 0
			for atom in self.pkgs[pkg][0][0]:
				for p in self.pkgs:
					# XXX: Comparing keys is a hack to make things a little quicker
					# -- jstubbs
					if p.key != atom.key:
						continue
					b = atom.match(p)
					if b and not atom.blocks:
						continue
					if atom.blocks: # Negatively weight existing blocks wrt choice
						c = self.pkgs[pkg][0][1]
					else:
						c = 1
					for index in self.pkgs[pkg][0][0][atom]:
						indices[index] += c
			reindexed = {}
			for index in indices:
				if indices[index] not in reindexed:
					reindexed[indices[index]] = [index]
				else:
					reindexed[indices[index]]+= [index]
			indices = reindexed.keys()
			indices.sort()
			# This arbitrarily choosing should be replaced by package.prefer
			# -- jstubbs
			reindexed[indices[0]].sort()
			chosen_index = reindexed[indices[0]][0]
			combination = []
			for atom in self.pkgs[pkg][0][0]:
				if chosen_index in self.pkgs[pkg][0][0][atom]:
					combination.append(atom)
			self.pkgs[pkg][1] = combination
			self._add_deps(pkg, combination)
		for pkg in self.pkgs:
			for atom in self.atoms:
				# XXX: Comparing keys is a hack to make things a little quicker
				# -- jstubbs
				if atom.key != pkg.key:
					continue
				if atom.match(pkg):
					self.pkgs[pkg][2].append(atom)
					self.atoms[atom][1].append(pkg)
		for pkg in self.pkgs:
			if not pkg.metapkg:
				continue
			redirected_atoms = []
			for parent_atom in self.pkgs[pkg][2]:
				if not parent_atom.blocks:
					continue
				redirected_atoms.append(parent_atom)
				for parent_pkg in self.atoms[parent_atom][0]:
					for child_atom in self.pkgs[pkg][1]:
						if child_atom.blocks or child_atom.match(parent_pkg):
							continue
						for child_pkg in self.atoms[child_atom][1]:
							self.pkgs[child_pkg][2].append(parent_atom)
							self.atoms[parent_atom][1].append(child_pkg)
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


def multiply_matrix(mat1, mat2):
	mat3 = [ { }, mat1[1] * mat2[1] ]

	for key in mat1[0]:
		mat3[0][key] = {}
		for x in mat1[0][key]:
			offset = x * mat2[1]
			for y in range(mat2[1]):
				mat3[0][key][ offset + y ] = True

	for key in mat2[0]:
		if key not in mat3[0]:
			mat3[0][key] = {}
		for x in range(mat1[1]):
			offset = x * mat2[1]
			for y in mat2[0][key]:
				mat3[0][key][ offset + y ] = True

	return mat3


def combinations(restrict):
	# [ { atom : [ combination index ] } , combination count ]
	ret = [{}, 0]

	if isinstance(restrict, OrRestriction):
		# XXX: OrRestrictions currently contain a single DepSet that contains
		# the Or'd elements. This seems broken to me.
		# -- jstubbs
		for element in restrict[0]:
			if isinstance(element, atom):
				if element not in ret[0]:
					ret[0][element] = {}
				ret[0][element][ret[1]] = True
				ret[1] += 1
			else:
				ret = multiply_matrix(ret, combinations(element))
	else:
		# already_seen hack kills off exponentialness from duplicate Or deps.
		# Need a clean way to detect if the current matrix already contains
		# the restriction to be added.
		# -- jstubbs
		already_seen = {}

		nonatoms = []
		for element in restrict:
			myhash = hash(element)
			if myhash in already_seen:
				continue
			already_seen[myhash] = True
			if isinstance(element, atom):
				ret[0][element] = [0]
			else:
				nonatoms.append(element)
		ret[1] = 1
		for element in nonatoms:
			ret = multiply_matrix(ret, combinations(element))

	return ret
