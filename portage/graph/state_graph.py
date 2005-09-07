
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
		if self.pkgs[pkg][0][1] <= 1:
			self.pkgs[pkg][1].union_update(sets.Set(self.pkgs[pkg][0][0].keys()))
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
			if self.pkgs[pkg][1] and self.pkgs[pkg][0][1] > 1:
				self._remove_deps(pkg)
				self.pkgs[pkg][1].clear()
		for pkg in self.pkgs:
			if self.pkgs[pkg][0][1] <= 1:
				continue
			usable = sets.Set(range(self.pkgs[pkg][0][1]))
			for atom in self.pkgs[pkg][0][0]:
				matched = False
				for child in self.pkgs:
					# XXX: Comparing keys is a hack to make things a little quicker
					# -- jstubbs
					if atom.key != child.key:
						continue
					if atom.match(child):
						matched = not atom.blocks
						break
				if not matched:
					usable.difference_update(self.pkgs[pkg][0][0][atom])
				if not usable:
					break
			if usable:
				index = usable.pop()
				for atom in self.pkgs[pkg][0][0]:
					if index in self.pkgs[pkg][0][0][atom]:
						self.pkgs[pkg][1].add(atom)
				self._add_deps(pkg)
			else:
				raise NotImplementedError("blocks and/or unresolvable atoms in all combinations")
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


def multiply_matrix(mat1, mat2):
	mat3 = [ { }, mat1[1] * mat2[1] ]

	for key in mat1[0]:
		mat3[0][key] = sets.Set()
		for x in mat1[0][key]:
			offset = x * mat2[1]
			for y in range(mat2[1]):
				mat3[0][key].add(offset)

	for key in mat2[0]:
		if key not in mat3[0]:
			mat3[0][key] = sets.Set()
		for x in range(mat1[1]):
			offset = x * mat2[1]
			for y in mat2[0][key]:
				mat3[0][key].add(offset + y)

	return simplify_matrix(mat3)


def simplify_matrix(mat):
	all_combs = {}
	for key in mat[0]:
		for index in mat[0][key]:
			if index not in all_combs:
				all_combs[index] = sets.Set([key])
			else:
				all_combs[index].add(key)

	reqd_combs = []
	for orig in all_combs:
		comb = all_combs[orig]
		index = 0
		while index < len(reqd_combs):
			if comb.issuperset(reqd_combs[index]):
				break
			elif comb.issubset(reqd_combs[index]):
				del reqd_combs[index]
			else:
				index += 1
		if index == len(reqd_combs):
			reqd_combs.append(comb)

	ret = [{}, len(reqd_combs)]
	index = 0
	for comb in reqd_combs:
		for key in comb:
			if key not in ret[0]:
				ret[0][key] = sets.Set([index])
			else:
				ret[0][key].add(index)
		index += 1

	return ret


def combinations(restrict):
	# [ { atom : Set( combination index ) } , combination count ]
	ret = [{}, 0]

	if isinstance(restrict, OrRestriction):
		# XXX: OrRestrictions currently contain a single DepSet that contains
		# the Or'd elements. This seems broken to me.
		# -- jstubbs
		for element in restrict[0]:
			if isinstance(element, atom):
				if element not in ret[0]:
					ret[0][element] = sets.Set()
				ret[0][element].add(ret[1])
				ret[1] += 1
			else:
				ret = multiply_matrix(ret, combinations(element))
	else:
		nonatoms = []
		for element in restrict:
			if isinstance(element, atom):
				ret[0][element] = sets.Set([0])
			else:
				nonatoms.append(element)
		ret[1] = 1
		ret = simplify_matrix(ret)
		for element in nonatoms:
			ret = multiply_matrix(ret, combinations(element))

	return ret
