# Copyright: 2005 Jason Stubbs <jstubbs@gentoo.org>
# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2


"""gentoo ebuild specific base package class"""


import re
from base import base
from pkgcore.util.currying import post_curry
from pkgcore.util.caching import WeakInstMeta
from pkgcore.package import atom, errors

suffix_regexp = re.compile("^(alpha|beta|rc|pre|p)(\\d*)$")
suffix_value = {"pre": -2, "p": 1, "alpha": -4, "beta": -3, "rc": -1}

# while the package section looks fugly, there is a reason for it- to prevent version chunks from showing up in the package

parser = re.compile("^(?P<key>(?P<category>(?:[a-zA-Z0-9+-]+)(?:/[a-zA-Z0-9+-]+)*)/" + \
	"(?P<package>[a-zA-Z0-9+][a-zA-Z0-9_+]*(?:-(?:[0-9]+[a-zA-Z+]{2,}[_+a-zA-Z0-9]*|[a-zA-Z+][a-zA-Z0-9+_]*))*))" + \
	"(?:-(?P<fullver>(?P<version>(?:cvs\\.)?(?:\\d+)(?:\\.\\d+)*[a-z]?(?:_(p(?:re)?|beta|alpha|rc)\\d*)*)" + \
	"(?:-r(?P<revision>\\d+))?))?$")


class native_CPV(object):

	"""
	base ebuild package class

        @ivar category: str category
        @ivar package: str package
	@ivar key: strkey (cat/pkg)
        @ivar version: str version
        @ivar revision: int revision
	@ivar versioned_atom: atom matching this exact version
	@ivar unversioned_atom: atom matching all versions of this package
	@cvar _get_attr: mapping of attr:callable to generate attributes on the fly
	"""

#	__metaclass__ = WeakInstMeta

#	__inst_caching__ = True

	def __init__(self, cpvstr):
		"""
		@param cpvstr: cat/pkg-ver[-rev] of an ebuild package.  See L{parser} for allowed syntax
		@type cpvstr: string
		"""
		self.__dict__["cpvstr"] = cpvstr
		m = parser.match(self.cpvstr)
		if not m:
			raise errors.InvalidCPV(self.cpvstr)
		self.__dict__.update(m.groupdict())
		r = self.__dict__["revision"]
		if r is not None:
			self.__dict__["revision"] = int(r)

	def __hash__(self):
		return hash(self.cpvstr)

	def __repr__(self):
		return '<%s cpvstr=%s @%#8x>' % (
			self.__class__.__name__, self.cpvstr, id(self))

	def __str__(self):
		return self.cpvstr

	def __setattr__(self, name, value):
		raise AttributeError(name)

	def __eq__(self, other):
		if isinstance(other, CPV):
			return self.cpvstr == other.cpvstr
		return False

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


def native_ver_cmp(ver1, rev1, ver2, rev2):

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
		for x in xrange(max(len_list)):

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
	for x in xrange(max(parts1_len, parts2_len)):

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

fake_cat = "fake"
fake_pkg = "pkg"
def cpy_ver_cmp(ver1, rev1, ver2, rev2):
	if ver1 == ver2:
		return cmp(rev1, rev2)
	c = cmp(cpy_CPV(ver1, fake_cat, fake_pkg), cpy_CPV(ver2, fake_cat, fake_pkg))
	if c != 0:
		return c
	return cmp(rev1, rev2)


try:
	from _cpv import CPV as cpy_CPV
	base_CPV = cpy_CPV
	ver_cmp = cpy_ver_cmp
	cpy_builtin = True
except ImportError:
	base_CPV = native_CPV
	ver_cmp = native_ver_cmp
	cpy_builtin = False


class CPV(base, base_CPV):

	"""
	base ebuild package class

        @ivar category: str category
        @ivar package: str package
	@ivar key: strkey (cat/pkg)
        @ivar version: str version
        @ivar revision: int revision
	@ivar versioned_atom: atom matching this exact version
	@ivar unversioned_atom: atom matching all versions of this package
	@cvar _get_attr: mapping of attr:callable to generate attributes on the fly
	"""

#	__metaclass__ = WeakInstMeta

#	__inst_caching__ = True

	_get_attr = {}

	def __repr__(self):
		return '<%s cpvstr=%s @%#8x>' % (
			self.__class__.__name__, self.cpvstr, id(self))

	def __setattr__(self, name, value):
		raise AttributeError(name)

	def __getattr__(self, attr):
		try:
			val = self.__dict__[attr] = self._get_attr[attr](self)
			return val
		except KeyError:
			raise AttributeError(attr)

	@property
	def versioned_atom(self):
		return atom.atom("=%s" % self.cpvstr)

	@property
	def unversioned_atom(self):
		return atom.atom(self.key)
