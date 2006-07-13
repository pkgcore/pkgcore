# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
restriction classes designed for package level matching
"""

import operator
from pkgcore.util.currying import pre_curry, pretty_docs
from pkgcore.restrictions import values, restriction, boolean
from pkgcore.util.demandload import demandload
demandload(globals(), "logging")

package_type = "package"

class PackageRestriction(restriction.base):
	"""
	package data restriction.  Inherit for anything that's more then cpv mangling please
	"""

	__slots__ = ("attr_split", "attr", "restriction")
	type = package_type
	__inst_caching__ = True

	def __init__(self, attr, restriction, negate=False):
		"""
		@param attr: package attribute to match against
		@param restriction: a L{pkgcore.restrictions.values.base} instance to pass attr to for matching
		@param negate: should the results be negated?
		"""
		super(PackageRestriction, self).__init__(negate=negate)
		self.attr_split = tuple(operator.attrgetter(x) for x in attr.split("."))
		self.attr = attr
		if not restriction.type == values.value_type:
			raise TypeError("restriction must be of a value type")
		self.restriction = restriction

	def __pull_attr(self, pkg):
		try:
			o = pkg
			for f in self.attr_split:
				o = f(o)
			return o
		except SystemExit:
			raise
		except AttributeError,ae:
			logging.debug("failed getting attribute %s from %s, exception %s" % \
				(self.attr, str(pkg), str(ae)))
			raise
		except Exception, e:
			logging.warn("caught unexpected exception accessing %s from %s, exception %s" % 
				(self.attr, str(pkg), str(e)))
			raise AttributeError

	def match(self, pkg):
		try:
			return self.restriction.match(self.__pull_attr(pkg)) ^ self.negate
		except AttributeError:
			return self.negate


	def force_False(self, pkg):
		if self.negate:
			return self.restriction.force_True(pkg, self.attr, self.__pull_attr(pkg))
		else:
			return self.restriction.force_False(pkg, self.attr, self.__pull_attr(pkg))

	def force_True(self, pkg):
		if self.negate:
			return self.restriction.force_False(pkg, self.attr, self.__pull_attr(pkg))
		else:
			return self.restriction.force_True(pkg, self.attr, self.__pull_attr(pkg))

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
		if s is None:
			return None
		if s == self.restriction:		return self
		elif s == other.restriction:	return other

		# this can probably bite us in the ass self or other is a derivative, and the other isn't.
		return self.__class__(self.attr, s)

	def __eq__(self, other):
		if self is other:
			return True
		if isinstance(other, self.__class__):
			try:
				return self.negate == self.negate and self.attr == other.attr and self.restriction == other.restriction
			except AttributeError, a:
				return False
		return False

	def __str__(self):
		s = self.attr+" "
		if self.negate:	
			s += "not "
		return s + str(self.restriction)

	def __repr__(self):
		if self.negate:
			string = '<%s attr=%r restriction=%r negated @%#8x>'
		else:
			string = '<%s attr=%r restriction=%r @%#8x>'
		return string % (
			self.__class__.__name__, self.attr, self.restriction, id(self))

class Conditional(PackageRestriction):

	"""
	base object representing a conditional package restriction
	
	used to control whether a payload of restrictions are accessible or not
	"""

	__slots__ = ("payload",)

	__inst_caching__ = True

	def __init__(self, attr, restriction, payload, **kwds):
		"""
		@param attr: attr to match against
		@param restriction: restriction to control whether or not the payload is accessible
		@param payload: payload data, whatever it may be.
		@param kwds: additional args to pass to L{PackageRestriction}
		"""
		super(Conditional, self).__init__(attr, restriction, **kwds)
		self.payload = tuple(payload)

	def __str__(self):
		return "( Conditional: %s payload: [ %s ] )" % (PackageRestriction.__str__(self), ", ".join(map(str, self.payload)))

	def __repr__(self):
		if self.negate:
			string = '<%s attr=%r restriction=%r payload=%r negated @%#8x>'
		else:
			string = '<%s attr=%r restriction=%r payload=%r @%#8x>'
		return string % (
			self.__class__.__name__, self.attr, self.restriction, self.payload,
			id(self))

	def __iter__(self):
		return iter(self.payload)


for m, l in [[boolean, ["AndRestriction", "OrRestriction", "XorRestriction"]], \
	[restriction, ["AlwaysBool"]]]:
	for x in l:
		o = getattr(m, x)
		doc = o.__doc__
		o = pre_curry(o, node_type=package_type)
		if doc is None:
			doc = ''
		else:
			# do this so indentation on pydoc __doc__ is sane
			doc = "\n".join(x.lstrip() for x in doc.split("\n")) +"\n"
			doc += "Automatically set to package type"
		globals()[x] = pretty_docs(o, doc)

del x, m, l, o, doc

AlwaysTrue = AlwaysBool(negate=True)
AlwaysFalse = AlwaysBool(negate=False)
