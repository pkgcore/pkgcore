# Copyright: 2005 Gentoo Foundation
# Author(s): Jason Stubbs (jstubbs@gentoo.org)
# License: GPL2
# $Id: cpv.py 1969 2005-09-04 07:38:17Z jstubbs $

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
		return 0

	match1 = ver_regexp.match(ver1)
	match2 = ver_regexp.match(ver2)

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
			if list1[i] > list2[i]:
				return 1
			return -1

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
			if suffix_value[s1[0]] - suffix_value[s2[0]]:
				return 1
			return -1
		if s1[1] != s2[1]:
			# it's possible that the s(1|2)[1] == ''
			# in such a case, fudge it.
			try:			r1 = int(s1[1])
			except ValueError:	r1 = 0
			try:			r2 = int(s2[1])
			except ValueError:	r2 = 0
			if r1 > r2:
				return 1
			return -1
	return cmp(rev1, rev2)
