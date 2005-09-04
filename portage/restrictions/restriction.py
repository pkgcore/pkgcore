# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: restriction.py 1969 2005-09-04 07:38:17Z jstubbs $

import re, logging

class base(object):
	"""base restriction matching object; overrides setattr to provide the usual write once trickery
	all derivatives *must* be __slot__ based"""

	__slots__ = ["negate"]
	package_matching = False

	def __init__(self, negate=False):
		self.negate = negate

#	def __setattr__(self, name, value):
#		import traceback;traceback.print_stack()
#		object.__setattr__(self, name, value)
#		try:	getattr(self, name)
#
#		except AttributeError:
#			object.__setattr__(self, name, value)
#		else:	raise AttributeError

	def match(self, *arg, **kwargs):
		raise NotImplementedError

	force_False = force_True = match
	def cmatch(self, pkg, *val):
		m=self.match(value)
		if m ^ self.negate:
			return True
		elif pkg == None or attr == None:
			return False
		elif self.negate:
			return pkg.request_disable(attr, value)
		return pkg.request_enable(attr, value)

	def intersect(self, other):
		return None

	def __len__(self):
		return 1

	def __repr__(self):
		return str(self)

	def __hash__(self):
		# XXX: This likely isn't actually unique. Something is needed
		# to uniquely identify restrictions though otherwise the object
		# pointer is used.
		# -- jstubbs
		if "_hash" not in self.__dict__:
			self.__dict__["_hash"] = hash(str(self))
		return self._hash

class AlwaysBoolMatch(base):
	__slots__ = base.__slots__
	def match(self, *a, **kw):		return self.negate
	def __str__(self):	return "always '%s'" % self.negate
	def cmatch(self, *a, **kw):		return self.negate

AlwaysFalse = AlwaysBoolMatch(False)
AlwaysTrue  = AlwaysBoolMatch(True)

