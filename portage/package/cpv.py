# Copyright: 2005 Gentoo Foundation
# Author(s): Jason Stubbs (jstubbs@gentoo.org)
# License: GPL2
# $Id: cpv.py 2037 2005-09-28 07:54:27Z jstubbs $

import re
from base import base

pkg_regexp = re.compile("^[a-zA-Z0-9]([-_+a-zA-Z0-9]*[+a-zA-Z0-9])?$")
ver_regexp = re.compile("^(cvs\\.)?(\\d+)((\\.\\d+)*)([a-z]?)((_(pre|p|beta|alpha|rc)\\d*)*)(-r(\\d+))?$")
suffix_regexp = re.compile("^(alpha|beta|rc|pre|p)(\\d*)$")
suffix_value = {"pre": -2, "p": 0, "alpha": -4, "beta": -3, "rc": -1}

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

		if name == "key":
			if self.category:
				self.__dict__["key"] = self.category +"/"+ self.package
			else:
				self.__dict__["key"] = self.package

		if name in ("version","revision","fullver"):
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
#					self.__dict__["revision"] = 0 # harring changed this
					self.__dict__["revision"] = None

				for x in myparts:
					if not ver_regexp.match(x):
						raise ValueError(self.mycpv)

				self.__dict__["version"] = "-".join(myparts)
		if name == "fullver":
			if self.version == None:
				self.__dict__["fullver"] = None
			elif self.revision == None:
				self.__dict__["fullver"] = self.version
			else:
				self.__dict__["fullver"] = "%s-r%i" % (self.version,self.revision)

		if name in self.__dict__:
			return self.__dict__[name]
		raise AttributeError,name

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
		return ver_cmp(self.version, self.revision, other.version, other.revision)


def ver_cmp(ver1, rev1, ver2, rev2):
	if ver1 == ver2:
		return cmp(rev1, rev2)

	parts1 = []
	parts2 = []

	for (ver, parts) in ((ver1, parts1), (ver2, parts2)):
		parts += ver.split("_")

	if parts1[0] != parts2[0]:
		ver_parts1 = parts1[0].split(".")
		if ver_parts1[-1][-1].isalpha():
			ver_parts1[-1:] = [ver_parts1[-1][:-1], str(ord(ver_parts1[-1][-1]))]
		ver_parts2 = parts2[0].split(".")
		if ver_parts2[-1][-1].isalpha():
			ver_parts2[-1:] = [ver_parts2[-1][:-1], str(ord(ver_parts2[-1][-1]))]

		if ver_parts1[0] == "cvs" and ver_parts2[0] != "cvs":
			return 1
		elif ver_parts1[0] != "cvs" and ver_parts2[0] == "cvs":
			return -1
		elif ver_parts1[0] == "cvs":
			ver_parts1[0].pop(0)
			ver_parts2[0].pop(0)

		for ver_parts in (ver_parts1, ver_parts2):
			while len(ver_parts) and int(ver_parts[-1]) == 0:
				del ver_parts[-1]

		for x in range(max(len(ver_parts1), len(ver_parts2))):

			if x == len(ver_parts1):
				return -1
			elif x == len(ver_parts2):
				return 1

			if ver_parts1[x] == ver_parts2[x]:
				continue

			if ver_parts1[x][0] == "0" or ver_parts2[x][0] == "0":
				v1 = float("0."+ver_parts1[x])
				v2 = float("0."+ver_parts2[x])
			else:
				v1 = int(ver_parts1[x])
				v2 = int(ver_parts2[x])

			if v1 == v2:
				continue
			return cmp(v1, v2)

	parts1.pop(0)
	parts2.pop(0)

	for x in range(max(len(parts1), len(parts2))):

		if x == len(parts1):
			match = suffix_regexp.match(parts2[x])
			val = -suffix_value[match.group(1)]
			if val:
				return val
			return -int("0"+match.group(2))
		if x == len(parts2):
			match = suffix_regexp.match(parts1[x])
			val = suffix_value[match.group(1)]
			if val:
				return val
			return int("0"+match.group(2))

		if parts1[x] == parts2[x]:
			continue

		match = suffix_regexp.match(parts1[x])
		(s1, n1) = (suffix_value[match.group(1)], int("0"+match.group(2)))
		match = suffix_regexp.match(parts2[x])
		(s2, n2) = (suffix_value[match.group(1)], int("0"+match.group(2)))

		if s1 != s2:
			return cmp(s1, s2)
		if n1 != n2:
			return cmp(n1, n2)

	return cmp(rev1, rev2)
