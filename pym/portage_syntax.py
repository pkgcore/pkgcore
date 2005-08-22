import re

from copy import *


pkg_regexp = re.compile("^[a-zA-Z0-9]([-_+a-zA-Z0-9]*[+a-zA-Z0-9])?$")
ver_regexp = re.compile("^(cvs\\.)?(\\d+)((\\.\\d+)*)([a-z]?)((_(pre|p|beta|alpha|rc)\\d*)*)(-r(\\d+))?$")
suffix_regexp = re.compile("^(alpha|beta|rc|pre|p)(\\d*)$")
suffix_value = {"pre": -2, "p": 0, "alpha": -4, "beta": -3, "rc": -1}

class CPV(object):

	"""
	Attributes

	str category
	str package
	str key (cat/pkg)
	str version
	int revision

	Methods

	int __hash__()
	str __repr__()
	int __cmp__(CPV)
	"""

	def __init__(self, cpvstr):
		if not isinstance(cpvstr, str):
			raise ValueError(cpvstr)
		self.__dict__["cpvstr"] = cpvstr
		self.__dict__["hash"] = hash(cpvstr)

	def __hash__(self):
		return self.hash

	def __repr__(self):
		return self.cpvstr

	def __setattr__(self, name, value):
		raise Exception()

	def __getattr__(self, name):

		if name == "category":
			myparts = self.cpvstr.split("/")
			if len(myparts) >= 2:
				if not pkg_regexp.match(myparts[0]):
					raise ValueError(self.cpvstr)
				self.__dict__["category"] = myparts[0]
			else:
				self.__dict__["category"] = None
			return self.category

		if name == "package":
			if self.category:
				myparts = self.cpvstr[len(self.category)+1:].split("-")
			else:
				myparts = self.cpvstr.split("-")
			if ver_regexp.match(myparts[0]):
				raise ValueError(self.cpvstr)
			pos = 1
			while pos < len(myparts) and not ver_regexp.match(myparts[pos]):
				pos += 1
			pkgname = "-".join(myparts[:pos])
			if not pkg_regexp.match(pkgname):
				raise ValueError(self.cpvstr)
			self.__dict__["package"] = pkgname
			return self.package

		if name == "key":
			if self.category:
				self.__dict__["key"] = self.category +"/"+ self.package
			else:
				self.__dict__["key"] = self.package
			return self.key

		if name == "version" or name == "revision":
			if self.category:
				myparts = self.cpvstr[len(self.category+self.package)+2:].split("-")
			else:
				myparts = self.cpvstr[len(self.package)+1:].split("-")

			if not myparts[0]:
				self.__dict__["version"] = None
				self.__dict__["revision"] = None

			else:
				if myparts[-1][0] == "r" and myparts[-1][1:].isdigit():
					self.__dict__["revision"] = int(myparts[-1][1:])
					myparts = myparts[:-1]
				else:
					self.__dict__["revision"] = 0

				for x in myparts:
					if not ver_regexp.match(x):
						raise ValueError(self.mycpv)

				self.__dict__["version"] = "-".join(myparts)

			if name == "version":
				return self.version
			else:
				return self.revision

		raise AttributeError(name)

	def __cmp__(self, other):

		if self.cpvstr == other.cpvstr:
			return 0

		if self.category and other.category and self.category != other.category:
			return cmp(self.category, other.category)

		if self.package and other.package and self.package != other.package:
			return cmp(self.package, other.package)

		if self.version != other.version:

			if self.version is None:
				raise ValueError(self)

			if other.version is None:
				raise ValueError(other)

			match1 = ver_regexp.match(self.version)
			match2 = ver_regexp.match(other.version)

			# shortcut for cvs ebuilds (new style)
			if match1.group(1) and not match2.group(1):
				return 1
			elif match2.group(1) and not match1.group(1):
				return -1

			# building lists of the version parts before the suffix
			# first part is simple
			list1 = [int(match1.group(2))]
			list2 = [int(match2.group(2))]

			# this part would greatly benefit from a fixed-length version pattern
			if len(match1.group(3)) or len(match2.group(3)):
				vlist1 = match1.group(3)[1:].split(".")
				vlist2 = match2.group(3)[1:].split(".")
				for i in range(0, max(len(vlist1), len(vlist2))):
					if len(vlist1) <= i or len(vlist1[i]) == 0:
						list1.append(0)
						list2.append(int(vlist2[i]))
					elif len(vlist2) <= i or len(vlist2[i]) == 0:
						list1.append(int(vlist1[i]))
						list2.append(0)
					# Let's make life easy and use integers unless we're forced to use floats
					elif (vlist1[i][0] != "0" and vlist2[i][0] != "0"):
						list1.append(int(vlist1[i]))
						list2.append(int(vlist2[i]))
					# now we have to use floats so 1.02 compares correctly against 1.1
					else:
						list1.append(float("0."+vlist1[i]))
						list2.append(float("0."+vlist2[i]))

			# and now the final letter
			if len(match1.group(5)):
				list1.append(ord(match1.group(5)))
			if len(match2.group(5)):
				list2.append(ord(match2.group(5)))

			for i in range(0, max(len(list1), len(list2))):
				if len(list1) <= i:
					return -1
				elif len(list2) <= i:
					return 1
				elif list1[i] != list2[i]:
					return list1[i] - list2[i]

			# main version is equal, so now compare the _suffix part
			list1 = match1.group(6).split("_")[1:]
			list2 = match2.group(6).split("_")[1:]

			for i in range(0, max(len(list1), len(list2))):
				if len(list1) <= i:
					s1 = ("p","0")
				else:
					s1 = suffix_regexp.match(list1[i]).groups()
				if len(list2) <= i:
					s2 = ("p","0")
				else:
					s2 = suffix_regexp.match(list2[i]).groups()
				if s1[0] != s2[0]:
					return suffix_value[s1[0]] - suffix_value[s2[0]]
				if s1[1] != s2[1]:
					# it's possible that the s(1|2)[1] == ''
					# in such a case, fudge it.
					try:			r1 = int(s1[1])
					except ValueError:	r1 = 0
					try:			r2 = int(s2[1])
					except ValueError:	r2 = 0
					return r1 - r2

		return cmp(self.revision, other.revision)


class Atom(object):

	"""
	Attributes

	bool blocks
	str  operator
	bool glob_match
	CPV  cpv

	Methods
	int __hash__()
	str __str__()
	str __repr__()
	bool match(CPV)
	"""

	def __init__(self, atomstr):
		if not isinstance(atomstr, str):
			raise ValueError(atomstr)
		self.__dict__["atomstr"] = atomstr
		self.__dict__["hash"] = hash(atomstr)

	def __hash__(self):
		return self.hash

	def __str__(self):
		return self.atomstr

	def __repr__(self):
		return "Atom('" + self.atomstr + "')"

	def __setattr__(self, name, value):
		raise Exception()

	def __eq__(self, other):
		if isinstance(other, Atom):
			return hash(self) == other.hash
		return False

	def __copy__(self):
		return self

	def __getattr__(self, name):

		if "operator" not in self.__dict__:

			myatom = self.atomstr

			if myatom[0] == "!":
				self.__dict__["blocks"] = True
				myatom = myatom[1:]
			else:
				self.__dict__["blocks"] = False

			if myatom[0:2] in ["<=", ">="]:
				self.__dict__["operator"] = myatom[0:2]
				myatom = myatom[2:]
			elif myatom[0] in ["<", ">", "=", "~"]:
				self.__dict__["operator"] = myatom[0]
				myatom = myatom[1:]
			else:
				self.__dict__["operator"] = None

			if myatom[-1] == "*":
				self.__dict__["glob_match"] = True
				myatom = myatom[:-1]
			else:
				self.__dict__["glob_match"] = False

			self.__dict__["cpv"] = CPV(myatom)

			if self.operator != "=" and self.glob_match:
				raise ValueError(self.atomstr)

			if self.operator and not self.cpv.version:
				raise ValueError(self.atomstr)

			if not self.operator and self.cpv.version:
				raise ValueError(self.atomstr)

			if self.operator == "~" and self.cpv.revision:
				raise ValueError(self.atomstr)

			if self.glob_match and self.cpv.revision:
				raise ValueError(self.atomstr)

		if not self.__dict__.has_key(name):
			return self.cpv.__getattr__(name)

		return self.__dict__[name]

	def match(self, cpv):

		if self.cpv.category and cpv.category and self.cpv.category != cpv.category:
			return False

		if self.cpv.package and cpv.package and self.cpv.package != cpv.package:
			return False

		if not self.operator:
			return True

		if self.operator == "=":
			if self.glob_match and cpv.version.startswith(self.cpv.version):
				return True
			if self.cpv.version != cpv.version:
				return False
			if self.cpv.revision != cpv.revision:
				return False
			return True

		if self.operator == "~" and self.cpv.version == cpv.version:
			return True

		diff = cmp(self.cpv, cpv)

		if not diff:
			if self.operator == "<=" or self.operator == ">=":
				return True
			else:
				return False

		if diff > 0:
			if self.operator[0] == "<":
				return True
			else:
				return False

		#if diff < 0:
		if self.operator[0] == ">":
			return True
		#else:
		return False

	def with_key(self, key):
		return Atom(self.atomstr.replace(self.cpv.key, key))

	def intersects(self, atom):
		if self == atom:
			return True
		if self.cpv.key != atom.cpv.key:
			return False
		if self.blocks != atom.blocks:
			return False
		if not self.operator or not atom.operator:
			return True
		if self.cpv == other.cpv:
			if self.operator == atom.operator:
				return True
			if self.operator == "<":
				return (atom.operator[0] == "<")
			if self.operator == ">":
				return (other.operator[0] == ">" or other.operator == "~")
			if self.operator == "=":
				return (other.operator != "<" and other.operator != ">")
			if self.operator == "~" or self.operator == ">=":
				return (other.operator != "<")
			return (other.operator != ">")
		elif self.cpv.version == other.cpv.version:
			if self.cpv > other.cpv:
				if self.operator == "=" and other.operator == "~":
					return True
			elif self.operator == "~" and other.operator == "=":
					return True
		if self.operator in ["=","~"] and other.operator in ["=","~"]:
			return False
		if self.cpv > other.cpv:
			if self.operator in ["<","<="]:
				return True
			if other.operator in [">",">="]:
				return True
			return False
		if self.operator in [">",">="]:
			return True
		if other.operator in ["<","<="]:
			return True
		return False

	def encapsulates(self, atom):
		if not self.intersects(atom):
			return False

		if self.operator and not atom.operator:
			return False
		if not self.operator:
			return True

		if self.cpv == atom.cpv:
			if self.operator == other.operator:
				return True
			if other.operator == "=":
				return True
			if self.operator == "<=" and other.operator == "<":
				return True
			if self.operator == ">=" and other.operator == ">":
				return True
			return False
		elif self.cpv.version == other.cpv.version:
			if self.cpv < other.cpv and self.operator == "~":
				return true
		if self.cpv > other.cpv:
			if self.operator in ["<","<="] and other.operator not in [">",">="]:
				return True
			return False
		if self.operator in [">",">="] and other.operator not in ["<","<="]:
			return True
		return False





class UseCondition(object):

	_use_regex = re.compile("^!?[\\w-]+\?$")

	def can_parse(cls, condition_str):
		return (cls._use_regex.match(condition_str) is not None)
	can_parse = classmethod(can_parse)

	def __init__(self, condition_str):
		condition_str = condition_str[:-1]
		self.__dict__["_hash"] = hash(condition_str)
		self.__dict__["negated"] = (condition_str[0] == "!")
		if self.negated:
			self.__dict__["flag"] = condition_str[1:]
		else:
			self.__dict__["flag"] = condition_str

	def __setattr__(self, name, value):
		raise TypeError("UseCondition has only read-only attributes (assign to "+name+")")

	def __hash__(self):
		return self._hash

	def __eq__(self, other):
		return (isinstance(other, UseCondition) and self._hash == other._hash)

	def __copy__(self):
		return self

	def conflicts_with(self, other):
		return (self.flag == other.flag and self.negated != other.negated)


class ParseError(Exception):
	pass


class DependSpec(object):

	def __init__(self, dependstr="", element_class=str):
		dependstr = " ( ".join(dependstr.split("("))
		dependstr = " ) ".join(dependstr.split(")"))
		dependstr = " ".join(dependstr.split())
		self.__dict__["_origstr"] = dependstr
		self.__dict__["_str"] = None
		self.__dict__["_element_class"] = element_class
		self.__dict__["_needs_brackets"] = True
		self.__dict__["_specials"] = []
		self.__dict__["condition"] = None

	def __copy__(self):
		dependspec = self.__class__()
		dependspec.__dict__["_element_class"] = self._element_class
		dependspec.__dict__["_specials"] = self._specials[:]
		dependspec.__dict__["condition"] = copy(self.condition)
		dependspec.__dict__["_needs_brackets"] = self._needs_brackets
		self._parsed
		dependspec.__dict__["_elements"] = self._elements[:]
		dependspec.__dict__["_parsed"] = True
		return dependspec

	def __setattr__(self, name, value):
		raise TypeError("DependSpec has only read-only attributes (assign to "+name+")")

	def __str__(self):
		if self._str is not None:
			return self._str
		self._parsed
		mystr = []
		for element in self._elements:
			x = str(element)
			if x:
				if isinstance(element, DependSpec) and element._needs_brackets:
					x = "( "+x+" )"
				mystr.append(x)
		mystr = " ".join(mystr)
		if self.condition:
			mystr = str(self.condition)+" ( "+mystr+" )"
		self.__dict__["_str"] = mystr
		return mystr

	def _needs_brackets(self):
		return True

	def __hash__(self):
		return hash(str(self))

	def __eq__(self, other):
		return (isinstance(other, DependSpec) and str(self) == str(other))

	def __getattr__(self, name):
		if "_parsed" not in self.__dict__:
			self._parse()
		return self.__dict__[name]

	def __getitem__(self, idx):
		self._parsed
		return self._elements[idx]

	def __len__(self):
		self._parsed
		return len(self._elements)

	def _parse(self):
		dependstr = self._origstr
		if dependstr.count("(") != dependstr.count(")"):
			raise ParseError(dependstr)
		self.__dict__["_elements"] = []
		specials_found = []
		condition = None
		strlen = len(dependstr)
		pos = 0
		while pos != strlen:
			if dependstr[pos] == " ":
				pos += 1
				continue
			if dependstr[pos] == ")":
				raise ParseError(dependstr)
			if dependstr[pos] == "(":
				pos += 1
				bracket_count = 1
				nextpos = pos
				while bracket_count:
					nextpos_d = {}
					nextpos_d[dependstr.find("(", nextpos)] = True
					nextpos_d[dependstr.find(")", nextpos)] = True
					if -1 in nextpos_d:
						del nextpos_d[-1]
					nextpos = min(nextpos_d.keys())
					if dependstr[nextpos] == "(":
						bracket_count += 1
					else:
						bracket_count -= 1
					nextpos += 1
				element = self.__class__(dependstr[pos:nextpos-1])
				element.__dict__["_element_class"] = self._element_class
				if condition:
					element.__dict__["condition"] = condition
					condition = None
				pos = nextpos
				self._elements.append(element)
				continue
			nextpos_d = {strlen:True}
			nextpos_d[dependstr.find(" ", pos)] = True
			nextpos_d[dependstr.find("(", pos)] = True
			nextpos_d[dependstr.find(")", pos)] = True
			if -1 in nextpos_d:
				del nextpos_d[-1]
			nextpos = min(nextpos_d.keys())
			element = dependstr[pos:nextpos]
			if element in self._specials:
				specials_found += [(element, len(self._elements))]
			elif UseCondition.can_parse(element):
				if condition:
					raise ParseError(dependstr)
				condition = UseCondition(element)
			else:
				if condition:
					raise ParseError(dependstr)
				self._elements.append(self._element_class(element))
			pos = nextpos
		if condition:
			raise ParseError(dependstr)
		for special in specials_found:
			if special[1] == len(self._elements):
				raise ParseError(dependstr)
			try:
				self._do_special(special[0], special[1])
			except ParseError:
				raise ParseError(dependstr)
		self.__dict__["_parsed"] = True

	def all_conditions(self):
		cond_d = {}
		if self.condition:
			cond_d[self.condition] = True
			yield self.condition

		self._parsed
		for element in self._elements:
			if isinstance(element, DependSpec):
				for cond in element.all_conditions():
					if cond not in cond_d:
						cond_d[cond] = True
						yield cond

	def with_only_conditions(self, conditions):
		if self.condition and self.condition not in conditions:
			return self.__class__()
		self._parsed
		dependspec = copy(self)
		dependspec.__dict__["condition"] = None
		for idx in range(len(dependspec._elements)):
			if isinstance(dependspec._elements[idx], DependSpec):
				dependspec._elements[idx] = dependspec._elements[idx].with_only_conditions(conditions)
		return dependspec

	def _can_combine_with(self, other):
		return self.condition == other.condition

	def compacted(self):
		elements = []
		element_d = {}
		self._parsed
		for element in self._elements:
			if element in element_d:
				continue
			if isinstance(element, DependSpec):
				element = element.compacted()
				if not len(element._elements):
					continue
				if self._can_combine_with(element):
					for element in element._elements:
						if element in element_d:
							continue
						elements.append(element)
						element_d[element] = True
				else:
					elements.append(element)
					element_d[element] = True
			else:
				elements.append(element)
				element_d[element] = True
		if not elements:
			return self.__class__()
		dependspec = copy(self)
		dependspec.__dict__["_elements"] = elements
		return dependspec


class AtomDependSpec(DependSpec):

	def create_from(atoms, preferential=False):
		dependstr = []
		for atom in atoms:
			dependstr.append(str(atom))
		dependstr = " ".join(dependstr)
		if preferential:
			dependstr = "|| ( "+dependstr+" )"
		return AtomDependSpec(dependstr)
	create_from = staticmethod(create_from)

	def __init__(self, dependstr=""):
		super(self.__class__, self).__init__(dependstr, element_class=Atom)
		self.__dict__["preferential"] = False
		self.__dict__["_specials"] = ["||"]

	def __copy__(self):
		atomdependspec = super(self.__class__, self).__copy__()
		atomdependspec.__dict__["preferential"] = self.preferential
		return atomdependspec

	def __str__(self):
		if self._str is not None:
			return self._str
		mystr = super(self.__class__, self).__str__()
		if self.preferential:
			mystr = "|| ( "+mystr+" )"
		self.__dict__["_str"] = mystr
		return mystr

	def _do_special(self, special, idx):
		if not isinstance(self._elements[idx], AtomDependSpec) or self._elements[idx].preferential:
			raise ParseError()
		self._elements[idx].__dict__["preferential"] = True
		self._elements[idx].__dict__["_needs_brackets"] = False

	def _can_combine_with(self, other):
		if self.preferential != other.preferential:
			return False
		return super(self.__class__, self)._can_combine_with(other)

	def compacted(self):
		atomdependspec = super(self.__class__, self).compacted()
		if atomdependspec.preferential and len(atomdependspec._elements) <= 1:
			atomdependspec.__dict__["preferential"] = False
			atomdependspec.__dict__["_needs_brackets"] = True
			atomdependspec = atomdependspec.compacted()
		return atomdependspec

	def with_keys_transformed(self, key_map):
		atomdependspec = copy(self)
		atomdependspec._parsed
		for x in range(len(atomdependspec._elements)):
			if isinstance(atomdependspec._elements[x], AtomDependSpec):
				atomdependspec._elements[x] = atomdependspec._elements[x].with_keys_transformed()
			elif atomdependspec._elements[x].key in key_map:
				elements = []
				for newkey in key_map[atomdependspec._elements[x].key]:
					elements.append(atomdependspec._elements[x].with_key(newkey))
				atomdependspec._elements[x] = AtomDependSpec.create_from(elements, preferential=True)
		atomdependspec.__dict__["_str"] = None
		return atomdependspec

	def combinations(self):
		if not self._elements:
			return []

		if self.condition:
			raise NotImplementedError()

		combinations = []

		if self.preferential:
			for element in self._elements:
				if isinstance(element, AtomDependSpec):
					combinations += element.combinations()
				else:
					combinations += [[element]]
		else:
			singles = []
			others = []
			for element in self._elements:
				if isinstance(element, AtomDependSpec):
					others += [element.combinations()]
				else:
					singles += [element]
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
					combinations.append(newcomb)
					indexes[index] += 1
			else:
				combinations = [singles]
		return combinations
