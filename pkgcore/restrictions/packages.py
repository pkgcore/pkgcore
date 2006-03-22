# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.lists import unique
from pkgcore.util.currying import pre_curry, pretty_docs
from pkgcore.restrictions import values, restriction, boolean

package_type = "package"
class base(restriction.base):
	__slots__ = restriction.base.__slots__
	type = package_type

class Conditional(base):
	"""base object representing a conditional node"""

	__slots__ = ["cond", "negate", "restrictions"]
	__inst_caching__ = False
	
	def __initialize__(self, node, payload, negate=False):
		self.negate, self.cond, self.restrictions = negate, node, payload

	def __str__(self):	
		if self.negate:
			s = "!"+self.cond
		else:
			s = self.cond
		try:
			s2=" ".join(str(x) for x in self.restrictions)
		except TypeError:
			s2 = str(self.restrictions)
		return "%s? ( %s )" % (s, s2)

	def __iter__(self):
		return iter(self.restrictions)

	def clone_empty(self):
		return self.__class__(self.cond, [], negate=self.negate)


class PackageRestriction(base):
	"""cpv data restriction.  Inherit for anything that's more then cpv mangling please"""

	__slots__ = tuple(["attr_split", "attr", "restriction"] + base.__slots__)
	
	def __initialize__(self, attr, restriction, **kwds):
		super(PackageRestriction, self).__initialize__(**kwds)
		self.attr_split = attr.split(".")
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

for m, l in [[boolean, ["AndRestriction", "OrRestriction", "XorRestriction"]], \
	[restriction, ["AlwaysBool"]]]:
	for x in l:
		o = getattr(m, x)
		doc = o.__doc__
		o = pre_curry(o, package_type)
		if doc == None:
			doc = ''
		else:
			# do this so indentation on pydoc __doc__ is sane
			doc = "\n".join(map(lambda x:x.lstrip(), doc.split("\n"))) +"\n"
			doc += "Automatically set to package type"
		globals()[x] = pretty_docs(o, doc)

del x, m, l, o, doc

AlwaysTrue = AlwaysBool(True)
AlwaysFalse = AlwaysBool(False)

