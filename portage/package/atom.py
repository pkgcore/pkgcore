# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: atom.py 2279 2005-11-10 00:27:34Z ferringb $

from portage.restrictions import values, packages, boolean
from cpv import ver_cmp, CPV
from portage.util.lists import unique

class MalformedAtom(Exception):
	def __init__(self, atom, err=''):	self.atom, self.err = atom, err
	def __str__(self):	return "atom '%s' is malformed: error %s" % (self.atom, self.err)

class InvalidVersion(Exception):
	def __init__(self, ver, rev, err=''):	self.ver, self.rev, self.err = ver, rev, err
	def __str__(self):	return "Version restriction ver='%s', rev='%s', is malformed: error %s" % (self.ver, self.rev, self.err)


class VersionMatch(packages.base):
	__slots__ = tuple(["ver","rev", "vals", "droprev"])
	"""any overriding of this class *must* maintain numerical order of self.vals, see intersect for reason why
	vals also must be a tuple"""

	type = packages.package_type
	def __init__(self, operator, ver, rev=None, negate=False, **kwd):
		kwd["negate"] = False
		super(self.__class__, self).__init__(**kwd)
		self.ver, self.rev = ver, rev
		if operator not in ("<=","<", "=", ">", ">=", "~"):
			# XXX: hack
			raise InvalidVersion(self.ver, self.rev, "invalid operator, '%s'" % operator)

		if negate:
			if operator == "~":
				raise Exception("Cannot negate '~' operator")
			if "=" in operator:		operator = operator.strip("=")
			else:					operator += "="
			for x,v in (("<",">"),(">","<")):
				if x in operator:
					operator = operator.strip(x) + v
					break

		if operator == "~":
			self.droprev = True
			self.vals = (0,)
		else:
			self.droprev = False
			l=[]
			if "<" in operator:	l.append(-1)
			if "=" in operator:	l.append(0)
			if ">" in operator:	l.append(1)
			self.vals = tuple(l)

	def intersect(self, other, allow_hand_off=True):
		if not isinstance(other, self.__class__):
			if allow_hand_off:
				return other.intersect(self, allow_hand_off=False)
			return None

		if self.droprev or other.droprev:
			vc = ver_cmp(self.ver, None, other.ver, None)
		else:
			vc = ver_cmp(self.ver, self.rev, other.ver, other.rev)

		# ick.  28 possible valid combinations.
		if vc == 0:
			if 0 in self.vals and 0 in other.vals:
				for x in (-1, 1):
					if x in self.vals and x in other.vals:
						return self
				# need a '=' restrict.
				if self.vals == (0,):
					return self
				elif other.vals == (0,):
					return other
				return self.__class__("=", self.ver, rev=self.rev)

			# hokay, no > in each.  potentially disjoint
			for x, v in ((-1, "<"), (1,">")):
				if x in self.vals and x in other.vals:
					return self.__class__(v, self.ver, rev=self.rev)

			# <, > ; disjoint.
			return None

		if vc < 0:	vc = -1
		else:		vc = 1
		# this handles a node already containing the intersection
		for x in (-1, 1):
			if x in self.vals and x in other.vals:
				if vc == x:
					return self
				return other

		# remaining permutations are interesections
		for x in (-1, 1):
			needed = x * -1
			if (x in self.vals and needed in other.vals) or (x in other.vals and needed in self.vals):
				return AndRestriction(self, other)

		if vc == -1 and 1 in self.vals and 0 in other.vals:
				return self.__class__("=", other.ver, rev=other.rev)
		elif vc == 1 and -1 in other.vals and 0 in self.vals:
			return self.__class__("=", self.ver, rev=self.rev)
		# disjoint.
		return None

	def match(self, pkginst):
		if self.droprev:			r1, r2 = None, None
		else:							r1, r2 = self.rev, pkginst.revision

		return (ver_cmp(pkginst.version, r2, self.ver, r1) in self.vals) ^ self.negate

	def __str__(self):
		l = []
		for x in self.vals:
			if x == -1:		l.append("<")
			elif x == 0:	l.append("=")
			elif x == 1:	l.append(">")
		l.sort()
		l = ''.join(l)
		if self.droprev or self.rev == None:
			return "ver %s %s" % (l, self.ver)
		return "fullver %s %s-r%s" % (l, self.ver, self.rev)

class atom(boolean.AndRestriction):

#	__slots__ = ("glob","atom","blocks","op", "negate_vers","cpv","cpvstr", "use","slot", "hash","category",
#		"version","revision", "fullver", "package") \
#		+ tuple(boolean.AndRestriction.__slots__)
	
	def __init__(self, atom, negate_vers=False):
		boolean.AndRestriction.__init__(self, packages.package_type)

		atom = atom.strip()
		self.hash = hash(atom)

		pos=0
		while atom[pos] in ("<",">","=","~","!"):
			pos+=1
		if atom.startswith("!"):
			self.blocks  = True
			self.op = atom[1:pos]
		else:
			self.blocks = False
			self.op = atom[:pos]

		u = atom.find("[")
		if u != -1:
			# use dep
			u2 = atom.find("]", u)
			if u2 == -1:
				raise MalformedAtom(atom, "use restriction isn't completed")
			self.use = atom[u+1:u2].split(',')
			atom = atom[0:u]+atom[u2 + 1:]
		else:
			self.use = ()
		s = atom.find(":")
		if s != -1:
			if atom.find(":", s+1) != -1:
				raise MalformedAtom(atom, "second specification of slotting")
			# slot dep.
			self.slot = atom[s + 1:].rstrip().split(",")
			atom = atom[:s]
		else:
			self.slot = ()
		del u,s

		if atom.endswith("*"):
			self.glob = True
			self.atom = atom[pos:-1]
		else:
			self.glob = False
			self.atom = atom[pos:]
		self.negate_vers = negate_vers
		self.cpv = CPV(self.atom)
		# force jitting of it.
		del self.restrictions


	def __getattr__(self, attr):
		if attr in ("category", "package", "version", "revision", "cpvstr", "fullver", "key"):
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
			if self.use:
				false_use = map(lambda x: x[1:], filter(lambda x: x.startswith("-"), self.use))
				true_use = filter(lambda x: not x.startswith("-"), self.use)
				if false_use:
					# XXX: convert this to a value AndRestriction whenever harring gets off his ass and
					# decides another round of tinkering with restriction subsystem is viable (burnt out now)
					# ~harring
					r.append(packages.PackageRestriction("use", values.ContainmentMatch(all=True, *false_use), negate=True))
				if true_use:
					r.append(packages.PackageRestriction("use", values.ContainmentMatch(all=True, *true_use)))
				if self.slot:
					r.append(packages.PackageRestriction("slot", values.ContainmentMatch(*self.slot)))
#			self.__dict__[attr] = r
			setattr(self, attr, r)
			return r

		raise AttributeError(attr)

	def atom_str(self):
		s = ""
		if self.blocks:			s+="!"
		s+=self.op+self.category+"/"+self.package
		if self.version:		s+="-"+self.fullver
		if self.glob:			s+="*"
		return s

	def __str__(self):
		return self.atom_str()

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
		if c != 0:	return c
		c = cmp(self.package, other.package)
		if c != 0:	return c
		c = ver_cmp(self.version, self.revision, other.version, other.revision)
		if c != 0:	return c
		return cmp(self.op, other.op)
