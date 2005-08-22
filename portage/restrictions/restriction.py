# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

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

class AlwaysBoolMatch(base):
	__slots__ = base.__slots__
	def match(self, *a, **kw):		return self.negate
	def __str__(self):	return "always '%s'" % self.negate
	def cmatch(self, *a, **kw):		return self.negate

AlwaysFalse = AlwaysBoolMatch(False)
AlwaysTrue  = AlwaysBoolMatch(True)

