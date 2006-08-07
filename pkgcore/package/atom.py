# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
gentoo ebuild atom, should be generalized into an agnostic base
"""

from pkgcore.restrictions import values, packages, boolean, restriction
from pkgcore.util.compatibility import all
import cpv

class MalformedAtom(Exception):
	def __init__(self, atom, err=''):
		self.atom, self.err = atom, err
	def __str__(self):
		return "atom '%s' is malformed: error %s" % (self.atom, self.err)

class InvalidVersion(Exception):
	def __init__(self, ver, rev, err=''):
		self.ver, self.rev, self.err = ver, rev, err
	def __str__(self):
		return "Version restriction ver='%s', rev='%s', is malformed: error %s" % (self.ver, self.rev, self.err)


# TODO: change values.EqualityMatch so it supports le, lt, gt, ge, eq, ne ops, and convert this to it.

class VersionMatch(restriction.base):

	"""
	package restriction implementing gentoo ebuild version comparison rules

	any overriding of this class *must* maintain numerical order of self.vals, see intersect for reason why
	vals also must be a tuple
	"""
	
	__slots__ = ("ver", "rev", "vals", "droprev", "negate")

	__inst_caching__ = True
	type = packages.package_type
	attr = "fullver"
	
	def __init__(self, operator, ver, rev=None, negate=False, **kwd):
		"""
		@param operator: version comparison to do, valid operators are ('<', '<=', '=', '>=', '>', '~')
		@type operator: string
		@param ver: version to base comparison on
		@type ver: string
		@param rev: revision to base comparison on
		@type rev: None (no rev), or an int
		@param negate: should the restriction results be negated; currently forced to False
		"""
		
		kwd["negate"] = False
		super(self.__class__, self).__init__(**kwd)
		self.ver, self.rev = ver, rev
		if operator not in ("<=", "<", "=", ">", ">=", "~"):
			# XXX: hack
			raise InvalidVersion(self.ver, self.rev, "invalid operator, '%s'" % operator)

		self.negate = negate
		if operator == "~":
			if ver is None:
				raise ValueError("for ~ op, version must be something other then None")
			self.droprev = True
			self.vals = (0,)
		else:
			self.droprev = False
			l = []
			if "<" in operator:	l.append(-1)
			if "=" in operator:	l.append(0)
			if ">" in operator:	l.append(1)
			self.vals = tuple(sorted(l))

	def match(self, pkginst):
		if self.droprev:
			r1, r2 = None, None
		else:
			r1, r2 = self.rev, pkginst.revision

		return (cpv.ver_cmp(pkginst.version, r2, self.ver, r1) in self.vals) != self.negate

	def __str__(self):
		l = []
		for x in self.vals:
			if x == -1:		l.append("<")
			elif x == 0:	l.append("=")
			elif x == 1:	l.append(">")
		l.sort()
		l = ''.join(l)
		if self.negate:
			n = "not "
		else:
			n = ''
		if self.droprev or self.rev is None:
			return "ver %s%s %s" % (n, l, self.ver)
		return "ver-rev %s%s %s-r%s" % (n, l, self.ver, self.rev)

	@staticmethod
	def _convert_ops(inst):
		if inst.negate:
			if inst.droprev:
				return inst.vals
			return tuple(sorted(set((-1,0,1)).difference(inst.vals)))
		return inst.vals

	def __eq__(self, other):
		if self is other:
			return True
		if isinstance(other, self.__class__):
			if self.droprev != other.droprev or self.ver != other.ver \
				or self.rev != other.rev:
				return False
			return self._convert_ops(self) == self._convert_ops(other)

		return False

	def __hash__(self):
		return hash((self.droprev, self.ver, self.rev, self.negate, self.vals))

class atom(boolean.AndRestriction):

	"""currently implements gentoo ebuild atom parsing, should be converted into an agnostic dependency base thought
	"""
	
	__slots__ = (
		"glob", "atom", "blocks", "op", "negate_vers", "cpv", "cpvstr", "use",
		"slot", "hash", "category", "version", "revision", "fullver", "package", "key")

	type = packages.package_type

	__inst_caching__ = True

	def __init__(self, atom, negate_vers=False):
		"""
		@param atom: string, see gentoo ebuild atom syntax
		"""
		boolean.AndRestriction.__init__(self)

		atom = orig_atom = atom.strip()
		self.hash = hash(atom)

		self.blocks = atom[0] == "!"
		if self.blocks:
			pos = 1
		else:
			pos = 0
		while atom[pos] in ("<", ">", "=", "~"):
			pos += 1
		if self.blocks:
			self.op = atom[1:pos]
		else:
			self.op = atom[:pos]

		u = atom.find("[")
		if u != -1:
			# use dep
			u2 = atom.find("]", u)
			if u2 == -1:
				raise MalformedAtom(atom, "use restriction isn't completed")
			self.use = atom[u+1:u2].split(',')
			if not all(x.rstrip("-") for x in self.use):
				raise MalformedAtom(atom, "cannot have empty use deps in use restriction")
			atom = atom[0:u]+atom[u2 + 1:]
		else:
			self.use = ()
		s = atom.find(":")
		if s != -1:
			if atom.find(":", s+1) != -1:
				raise MalformedAtom(atom, "second specification of slotting")
			# slot dep.
			self.slot = atom[s + 1:].rstrip()
			if not self.slot:
				raise MalformedAtom(atom, "cannot have empty slot deps in slot restriction")
			atom = atom[:s]
		else:
			self.slot = None
		del u,s

		if atom.endswith("*"):
			if self.op != "=":
				raise MalformedAtom(orig_atom, "range operators on a range are nonsencial, drop the globbing or use =cat/pkg* or !=cat/pkg*, not %s" % self.op)
			self.glob = True
			self.atom = atom[pos:-1]
			# may have specified a period to force calculation limitation there- hence rstrip'ing it for the cpv generation
		else:
			self.glob = False
			self.atom = atom[pos:]
		self.negate_vers = negate_vers
		if "~" in self.op:
			if self.cpv.version is None:
				raise MalformedAtom(orig_atom, "~ operator requires a version")
		# force jitting of it.
		del self.restrictions

	def __repr__(self):
		atom = self.op + self.atom
		if self.blocks:
			atom = '!' + atom
		if self.glob:
			atom = atom + '*'
		attrs = [atom]
		if self.use:
			attrs.append('use=' + repr(self.use))
		if self.slot:
			attrs.append('slot=' + repr(self.slot))
		return '<%s %s @#%x>' % (
			self.__class__.__name__, ' '.join(attrs), id(self))

	def iter_dnf_solutions(self, full_solution_expansion=False):
		if full_solution_expansion:
			return boolean.AndRestriction.iter_dnf_solutions(self, full_solution_expansion=True)
		return iter([[self]])

	def cnf_solutions(self, full_solution_expansion=False):
		if full_solution_expansion:
			return boolean.AndRestriction.cnf_solutions(self, full_solution_expansion=True)
		return [[self]]

	def __getattr__(self, attr):
		if attr == "cpv":
			c = cpv.CPV(self.atom)
			setattr(self, "cpv", c)
			return c
		elif attr in ("category", "package", "version", "revision", "cpvstr", "fullver", "key"):
			g = getattr(self.cpv, attr)
			# Commenting this doubles the time taken in StateGraph.recalculate_deps()
			# -- jstubbs
			setattr(self, attr, g)
			return g
		elif attr == "restrictions":
			r = [packages.PackageRestriction("package", values.StrExactMatch(self.package))]
			try:
				cat = self.category
				r.append(packages.PackageRestriction("category", values.StrExactMatch(cat)))
			except AttributeError:
				pass
			if self.version:
				if self.glob:
					r.append(packages.PackageRestriction("fullver", values.StrGlobMatch(self.fullver)))
				else:
					r.append(VersionMatch(self.op, self.version, self.revision, negate=self.negate_vers))
			elif self.op:
				raise MalformedAtom(str(self), "cannot specify a version operator without a version")
				
			if self.use:
				false_use = [x[1:] for x in self.use if x[0] == "-"]
				true_use = [x for x in self.use if x[0] != "-"]
				if false_use:
					# XXX: convert this to a value AndRestriction whenever harring gets off his ass and
					# decides another round of tinkering with restriction subsystem is viable (burnt out now)
					# ~harring
					r.append(packages.PackageRestriction("use", values.ContainmentMatch(negate=True, all=True, *false_use)))
				if true_use:
					r.append(packages.PackageRestriction("use", values.ContainmentMatch(all=True, *true_use)))
			if self.slot is not None:
				r.append(packages.PackageRestriction("slot", values.StrExactMatch(self.slot)))
			setattr(self, attr, tuple(r))
			return r

		raise AttributeError(attr)

	def __str__(self):
		s = ""
		if self.blocks:
			s += "!"
		s += self.op + self.category + "/" + self.package
		if self.version:
			s += "-"+self.fullver
		if self.glob:
			s += "*"
		if self.use:
			s += "[%s]" % ",".join(self.use)
		if self.slot:
			s += ":%s" % ",".join(self.slot)
		return s

	def __hash__(self):
		return self.hash

	def __iter__(self):
		return iter(self.restrictions)

	def __getitem__(self, index):
		return self.restrictions[index]

	def __cmp__(self, other):
		if not isinstance(other, self.__class__):
			raise TypeError("other isn't of %s type, is %s" % (self.__class__, other.__class__))
		c = cmp(self.category, other.category)
		if c:
			return c
		c = cmp(self.package, other.package)
		if c:
			return c
		c = cpv.ver_cmp(self.version, self.revision, other.version, other.revision)
		if c:
			return c

		return cmp(self.op, other.op)

	def __ne__(self, other):
		return self is not other

	def __eq__(self, other):
		return self is other
