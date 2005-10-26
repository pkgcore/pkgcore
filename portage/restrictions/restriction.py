# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: restriction.py 2196 2005-10-26 22:23:18Z ferringb $


class base(object):
	"""base restriction matching object; overrides setattr to provide the usual write once trickery
	all derivatives *must* be __slot__ based"""

	__slots__ = ["negate", "_hash"]
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

	def intersect(self, other):
		return None

	def __len__(self):
		return 1

	def __repr__(self):
		return str(self)

	def __str__(self):
		# without this __repr__ recurses...
		raise NotImplementedError

	def __hash__(self):
		# XXX: This likely isn't actually unique. Something is needed
		# to uniquely identify restrictions though otherwise the object
		# pointer is used.
		# -- jstubbs
		if not hasattr(self, '_hash'):
			self._hash = hash(str(self))
		return self._hash


class AlwaysBool(base):
	__slots__ = ["type"] + base.__slots__
	
	def __init__(self, package_type, negate=False):
		self.type, self.negate  = package_type, negate

	def match(self, *a, **kw):
		return self.negate

	def __str__(self):
		return "always '%s'" % self.negate
