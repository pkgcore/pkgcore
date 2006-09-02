# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
base restriction class
"""

from pkgcore.util import caching

class base(object):

	__metaclass__ = caching.WeakInstMeta
	__inst_caching__ = True

	"""
	base restriction matching object; overrides setattr to provide the usual write once trickery
	all derivatives *should* be __slot__ based (lot of instances may wind up in memory)
	"""

	__slots__ = ("negate",)
	package_matching = False

	def __init__(self, negate=False):
		"""
		@param negate: should the match results be negated?
		"""
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

	def force_False(self, *arg, **kwargs):
		return not self.match(*arg, **kwargs)
	
	def force_True(self, *arg, **kwargs):
		return self.match(*arg, **kwargs)

	def intersect(self, other):
		return None

	def __len__(self):
		return 1

	def __repr__(self):
		return str(self)

	def __str__(self):
		# without this __repr__ recurses...
		raise NotImplementedError


class AlwaysBool(base):
	"""
	restriction that always yields a specific boolean
	"""
	__slots__ = ("type",)

	__inst_caching__ = True

	def __init__(self, node_type=None, negate=False):
		"""
		@param node_type: the restriction type the instance should be, typically L{pkgcore.restrictions.packages.package_type},
		L{pkgcore.restrictions.values.value_type}
		@param negate: boolean to return for the match
		"""
		self.type, self.negate  = node_type, negate

	def match(self, *a, **kw):
		return self.negate

	def force_True(self, *a, **kw):
		return self.negate
	
	def force_False(self, *a, **kw):
		return not self.negate

	def __iter__(self):
		return iter([])

	def __str__(self):
		return "always '%s'" % self.negate


class Negate(base):

	"""
	wrap and negate a restriction instance
	"""

	__slots__ = ("type", "_restrict")
	__inst_caching__ = False
	
	def __init__(self, restrict):
		"""
		@param restrict: L{pkgcore.restrictions.restriction.base} instance to negate
		"""
		self.type = restrict.type
		self._restrict = restrict
		
	def match(self, *a, **kw):
		return not self._restrict.match(*a, **kw)

	def __str__(self):
		return "not (%s)" % self._restrict


class FakeType(base):

	"""
	wrapper to wrap and fake a node_type
	""" 

	__slots__ = ("type", "_restrict")
	__inst_caching__ = False
		
	def __init__(self, restrict, new_type):
		"""
		@param restrict: L{pkgcore.restrictions.restriction.base} instance to wrap
		@param new_type: new node_type
		"""
		self.type = new_type
		self._restrict = restrict
	
	def match(self, *a, **kw):
		return self._restrict.match(*a, **kw)

	def __str__(self):
		return "Faked type(%s): %s" % (self.type, self._restrict)


value_type = "values"
package_type = "package"
