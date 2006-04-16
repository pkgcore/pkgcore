# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.currying import pre_curry, pretty_docs
from pkgcore.restrictions import values, restriction, boolean
import logging

package_type = "package"

class PackageRestriction(restriction.base):
	"""cpv data restriction.  Inherit for anything that's more then cpv mangling please"""

	__slots__ = ("attr_split", "attr", "restriction")
	type = package_type
	
	def __init__(self, attr, restriction, **kwds):
		super(PackageRestriction, self).__init__(**kwds)
		self.attr_split = tuple(attr.split("."))
		self.attr = attr
		if not restriction.type == values.value_type:
			raise TypeError("restriction must be of a value type")
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


class Conditional(PackageRestriction):
	"""base object representing a conditional node"""

	__slots__ = ("payload",)

	__inst_caching__ = True

	def __init__(self, attr, restriction, payload, **kwds):
		super(Conditional, self).__init__(attr, restriction, **kwds)
		self.payload = tuple(payload)

	def __str__(self):
		return "( Conditional: %s payload: [ %s ] )" % (PackageRestriction.__str__(self), ", ".join(map(str, self.payload)))
	
	def __iter__(self):
		return iter(self.payload)


for m, l in [[boolean, ["AndRestriction", "OrRestriction", "XorRestriction"]], \
	[restriction, ["AlwaysBool"]]]:
	for x in l:
		o = getattr(m, x)
		doc = o.__doc__
		o = pre_curry(o, node_type=package_type)
		if doc == None:
			doc = ''
		else:
			# do this so indentation on pydoc __doc__ is sane
			doc = "\n".join(map(lambda x:x.lstrip(), doc.split("\n"))) +"\n"
			doc += "Automatically set to package type"
		globals()[x] = pretty_docs(o, doc)

del x, m, l, o, doc

AlwaysTrue = AlwaysBool(negate=True)
AlwaysFalse = AlwaysBool(negate=False)

