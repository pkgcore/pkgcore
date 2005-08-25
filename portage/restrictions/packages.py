# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: packages.py 1911 2005-08-25 03:44:21Z ferringb $

import restriction
import boolean
from portage.util.lists import unique
import values

class base(restriction.base):
	package_matching = True

class PackageRestriction(base):
	"""cpv data restriction.  Inherit for anything that's more then cpv mangling please"""

	__slots__ = tuple(["attr_split", "attr", "restriction"] + base.__slots__)
	
	def __init__(self, attr, restriction, **kwds):
		super(PackageRestriction, self).__init__(**kwds)
		self.attr_split = attr.split(".")
		self.attr = attr
		if not isinstance(restriction, values.base):
			raise TypeError("restriction must be of a restriction type")
		self.restriction = restriction

	def __pull_attr(self, pkg):
		try:
			o = pkg
			for x in self.attr_split:
				o = getattr(o, x)
			return o
		except AttributeError,ae:
			logging.debug("failed getting attribute %s from %s, exception %s" % \
				(self.attr, str(pkg), str(ae)))
			raise

	def match(self, pkg):
		try:
			return self.restriction.match(self.__pull_attr(pkg)) ^ self.negate
		except AttributeError:
			return self.negate
		

	def force_False(self, pkg):
#		import pdb;pdb.set_trace()
		if self.negate:
			i = self.restriction.force_True(pkg, self.attr, self.__pull_attr(pkg))
		else: 
			i = self.restriction.force_False(pkg, self.attr, self.__pull_attr(pkg))
		if isinstance(i, bool):
			yield i
		else:
			for x in i:
				yield True
		return

	def force_True(self, pkg):
#		import pdb;pdb.set_trace()
		if self.negate:
			i = self.restriction.force_False(pkg, self.attr, self.__pull_attr(pkg))
		else: 
			i = self.restriction.force_True(pkg, self.attr, self.__pull_attr(pkg))
		if isinstance(i, bool):
			yield i
		else:
			for x in i:
				yield True
		return
					

	def __getitem__(self, key):
		if not isinstance(self.restriction, boolean.base):
			if key != 0:
				raise IndexError("restriction isn't indexable")
			else:
				return self
		try:
			g = self.restriction[key]
		except TypeError:
			if key == 0:
				return self.restriction
			raise IndexError("index out of range")

	def __len__(self):
		if not isinstance(self.restriction, boolean.base):
			return 1
		return len(self.restriction) + 1

	def intersect(self, other):
		if self.negate != other.negate or self.attr != other.attr:
			return None
		if isinstance(self.restriction, other.restriction.__class__):
			s = self.restriction.intersect(other.restriction)
		elif isinstance(other.restriction, self.restriction.__class__):
			s = other.restriction.intersect(self.restriction)
		else:	return None
		if s == None:
			return None
		if s == self.restriction:		return self
		elif s == other.restriction:	return other

		# this can probably bite us in the ass self or other is a derivative, and the other isn't.
		return self.__class__(self.attr, s)

	def __eq__(self, other):
		return self.negate == self.negate and self.attr == other.attr and self.restriction == other.restriction

	def __str__(self):
		s = self.attr+" "
		if self.negate:	self.attr += "not "
		return s + str(self.restriction)


class AndRestriction(base, boolean.AndRestriction):
	__slots__ = tuple(unique(list(boolean.AndRestriction.__slots__) + base.__slots__))
	required_base = base
	

class OrRestriction(base, boolean.OrRestriction):
	__slots__ = tuple(unique(list(boolean.OrRestriction.__slots__) + base.__slots__))
	required_base = base

class XorRestriction(base, boolean.XorRestriction):
	__slots__ = tuple(unique(list(boolean.XorRestriction.__slots__) + base.__slots__))
	required_base = base

class AlwaysBoolRestriction(restriction.AlwaysBoolMatch, base):
	__slots__=("negate")
def __init__(self, val):
	self.negate = val
def match(self, *a):
	return self.negate
def force_False(self, *a):
	return self.negate == False
def force_True(self, *a):
	return self.negate == True

AlwaysTrue = AlwaysBoolRestriction(True)
AlwaysFalse = AlwaysBoolRestriction(True)
