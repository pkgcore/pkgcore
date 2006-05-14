# Copyright: 2005 Jason Stubbs <jstubbs@gentoo.org>
# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import re
from base import base
from pkgcore.util.currying import post_curry
from pkgcore.package import atom

pkg_regexp = re.compile("^[a-zA-Z0-9]([-_+a-zA-Z0-9]*[+a-zA-Z0-9])?$")
ver_regexp = re.compile("^(cvs\\.)?(\\d+)((\\.\\d+)*)([a-z]?)((_(pre|p|beta|alpha|rc)\\d*)*)(-r(\\d+))?$")
suffix_regexp = re.compile("^(alpha|beta|rc|pre|p)(\\d*)$")
suffix_value = {"pre": -2, "p": 1, "alpha": -4, "beta": -3, "rc": -1}

class CPV(base):

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

	_get_attr = {}

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

	def __getattr__(self, attr):
		try:
			val = self.__dict__[attr] = self._get_attr[attr](self)
			return val
		except KeyError:
			raise AttributeError(attr)

	def _get_category(self):
		myparts = self.cpvstr.split("/")
		if len(myparts) >= 2:
			# regexes suck. move away from them.
			if not pkg_regexp.match(myparts[0]):
				raise ValueError(self.cpvstr)
			return myparts[0]
		return None

	_get_attr["category"] = _get_category

	def _get_package(self):
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
		return pkgname

	_get_attr["package"] = _get_package

	def _get_key(self):
		if self.category:
			return self.category +"/"+ self.package
		return self.package

	_get_attr["key"] = _get_key

	def _split_version(self, attr):
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
				self.__dict__["revision"] = None

			for x in myparts:
				if not ver_regexp.match(x):
					raise ValueError(self.cpvstr)

			self.__dict__["version"] = "-".join(myparts)
			if self.__dict__["version"] is None:
				self.__dict__["fullver"] = None
			else:
				if self.version == None:
					self.__dict__["fullver"] = None
				elif self.revision == None:
					self.__dict__["fullver"] = self.version
				else:
					self.__dict__["fullver"] = "%s-r%i" % (self.version, self.revision)

		return self.__dict__[attr]

	_get_attr.update([(x, post_curry(_split_version, x)) for x in ("version", "fullver", "revision")])


	def __eq__(self, other):
		if not isinstance(other, self.__class__):
			return False
		return self.hash == other.hash

	def __cmp__(self, other):

		if self.cpvstr == other.cpvstr:
			return 0

		if self.category and other.category and self.category != other.category:
			return cmp(self.category, other.category)

		if self.package and other.package and self.package != other.package:
			return cmp(self.package, other.package)

		# note I chucked out valueerror, none checks on versions passed in.  I suck, I know.
		# ~harring
		# fails in doing comparison of unversioned atoms against versioned atoms
		return ver_cmp(self.version, self.revision, other.version, other.revision)

	@property
	def versioned_atom(self):
		return atom.atom("=%s" % self.cpvstr)


def ver_cmp(ver1, rev1, ver2, rev2):

	# If the versions are the same, comparing revisions will suffice.
	if ver1 == ver2:
		return cmp(rev1, rev2)

	# Split up the versions into dotted strings and lists of suffixes.
	parts1 = ver1.split("_")
	parts2 = ver2.split("_")

	# If the dotted strings are equal, we can skip doing a detailed comparison.
	if parts1[0] != parts2[0]:

		# First split up the dotted strings into their components.
		ver_parts1 = parts1[0].split(".")
		ver_parts2 = parts2[0].split(".")

		# And check if CVS ebuilds come into play. If there is only
		# one it wins by default. Otherwise any CVS component can
		# be ignored.
		if ver_parts1[0] == "cvs" and ver_parts2[0] != "cvs":
			return 1
		elif ver_parts1[0] != "cvs" and ver_parts2[0] == "cvs":
			return -1
		elif ver_parts1[0] == "cvs":
			del ver_parts1[0][0]
			del ver_parts2[0][0]

		# Pull out any letter suffix on the final components and keep
		# them for later.
		letters = []
		for ver_parts in (ver_parts1, ver_parts2):
			if ver_parts[-1][-1].isalpha():
				letters.append(ord(ver_parts[-1][-1]))
				ver_parts[-1] = ver_parts[-1][:-1]
			else:
				# Using -1 simplifies comparisons later
				letters.append(-1)

		# OPT: Pull length calculation out of the loop
		ver_parts1_len = len(ver_parts1)
		ver_parts2_len = len(ver_parts2)
		len_list = (ver_parts1_len, ver_parts2_len)

		# Iterate through the components
		for x in range(max(len_list)):

			# If we've run out components, we can figure out who wins
			# now. If the version that ran out of components has a
			# letter suffix, it wins. Otherwise, the other version wins.
			if x in len_list:
				if x == ver_parts1_len:
					return cmp(letters[0], 0)
				else:
					return cmp(0, letters[1])

			# If the string components are equal, the numerical
			# components will be equal too.
			if ver_parts1[x] == ver_parts2[x]:
				continue

			# If one of the components begins with a "0" then they
			# are compared as floats so that 1.1 > 1.02.
			if ver_parts1[x][0] == "0" or ver_parts2[x][0] == "0":
				v1 = float("0."+ver_parts1[x])
				v2 = float("0."+ver_parts2[x])
			else:
				v1 = int(ver_parts1[x])
				v2 = int(ver_parts2[x])

			# If they are not equal, the higher value wins.
			c = cmp(v1, v2)
			if c:	return c

		# The dotted components were equal. Let's compare any single
		# letter suffixes.
		if letters[0] != letters[1]:
			return cmp(letters[0], letters[1])

	# The dotted components were equal, so remove them from our lists
	# leaving only suffixes.
	del parts1[0]
	del parts2[0]

	# OPT: Pull length calculation out of the loop
	parts1_len = len(parts1)
	parts2_len = len(parts2)

	# Iterate through the suffixes
	for x in range(max(parts1_len, parts2_len)):

		# If we're at the end of one of our lists, we need to use
		# the next suffix from the other list to decide who wins.
		if x == parts1_len:
			match = suffix_regexp.match(parts2[x])
			val = suffix_value[match.group(1)]
			if val:	return cmp(0, val)
			return cmp(0, int("0"+match.group(2)))
		if x == parts2_len:
			match = suffix_regexp.match(parts1[x])
			val = suffix_value[match.group(1)]
			if val:	return cmp(val, 0)
			return cmp(int("0"+match.group(2)), 0)

		# If the string values are equal, no need to parse them.
		# Continue on to the next.
		if parts1[x] == parts2[x]:
			continue

		# Match against our regular expression to make a split between
		# "beta" and "1" in "beta1"
		match1 = suffix_regexp.match(parts1[x])
		match2 = suffix_regexp.match(parts2[x])

		# If our int'ified suffix names are different, use that as the basis
		# for comparison.
		c = cmp(suffix_value[match1.group(1)], suffix_value[match2.group(1)])
		if c:	return c

		# Otherwise use the digit as the basis for comparison.
		c = cmp(int("0"+match1.group(2)), int("0"+match2.group(2)))
		if c:	return c

	# Our versions had different strings but ended up being equal.
	# The revision holds the final difference.
	return cmp(rev1, rev2)
