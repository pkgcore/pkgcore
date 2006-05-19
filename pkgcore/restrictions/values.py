# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import re
from pkgcore.restrictions import restriction, boolean
from pkgcore.util.currying import pre_curry, pretty_docs
from pkgcore.util.compatibility import any

value_type = "values"

class base(restriction.base):
	"""base restriction matching object; overrides setattr to provide the usual write once trickery
	all derivatives *must* be __slot__ based"""

	__slots__ = ()

	type = value_type

	def force_True(self, pkg, attr, val):
		if self.match(val) ^ self.negate:
			return True
		elif self.negate:
			return pkg.request_disable(attr, val)
		return pkg.request_enable(attr, val)

	def force_False(self, pkg, attr, val):
		if self.match(val) ^ self.negate:
			return True
		elif self.negate:
			return pkg.request_enable(attr, val)
		return pkg.request_disable(attr, val)


class VersionRestriction(base):
	"""use this as base for version restrictions, gives a clue to what the restriction does"""
	__slots__ = ()


class StrMatch(base):
	""" Base string matching restriction.  all derivatives must be __slot__ based classes"""
	__slots__ = ("flags",)


class StrRegexMatch(StrMatch):
	#potentially redesign this to jit the compiled_re object
	__slots__ = ("regex", "compiled_re")

	__inst_caching__ = True

	def __init__(self, regex, CaseSensitive=True, **kwds):
		super(StrRegexMatch, self).__init__(**kwds)
		self.regex = regex
		flags = 0
		if not CaseSensitive:
			flags = re.I
		self.flags = flags
		self.compiled_re = re.compile(regex, flags)

	def match(self, value):
		return (self.compiled_re.match(str(value)) != None) ^ self.negate

	def intersect(self, other):
		if self.regex == other.regex and self.negate == other.negate and self.flags == other.flags:
			return self
		return None

	def __eq__(self, other):
		return self.regex == other.regex and self.negate == other.negate and self.flags == other.flags

	def __str__(self):
		if self.negate:	return "not like %s" % self.regex
		return "like %s" % self.regex


class StrExactMatch(StrMatch):
	__slots__ = ("exact", "flags")

	__inst_caching__ = True

	def __init__(self, exact, CaseSensitive=True, **kwds):
		super(StrExactMatch, self).__init__(**kwds)
		if not CaseSensitive:
			self.flags = re.I
			self.exact = str(exact).lower()
		else:
			self.flags = 0
			self.exact = str(exact)

	def match(self, value):
		if self.flags & re.I:
			return (self.exact == str(value).lower()) != self.negate
		else:	
			return (self.exact == str(value)) != self.negate

	def intersect(self, other):
		s1, s2 = self.exact, other.exact
		if other.flags and not self.flags:
			s1 = s1.lower()
		elif self.flags and not other.flags:
			s2 = s2.lower()
		if s1 == s2 and self.negate == other.negate:
			if other.flags:
				return other
			return self
		return None

	def __eq__(self, other):
		return self.exact == other.exact and self.negate == other.negate and self.flags == other.flags

	def __str__(self):
		if self.negate:
			return "!= "+self.exact
		return "== "+self.exact


class StrGlobMatch(StrMatch):

	__slots__ = ("glob", "prefix")

	__inst_caching__ = True

	def __init__(self, glob, CaseSensitive=True, prefix=True, **kwds):
		super(StrGlobMatch, self).__init__(**kwds)
		if not CaseSensitive:
			self.flags = re.I
			self.glob = str(glob).lower()
		else:
			self.flags = 0
			self.glob = str(glob)
		self.prefix = prefix

	def match(self, value):
		value = str(value)
		if self.flags & re.I:
			value = value.lower()
		if self.prefix:
			f = value.startswith
		else:
			f = value.endswith
		return f(self.glob) ^ self.negate

	def intersect(self, other):
		if self.match(other.glob):
			if self.negate == other.negate:
				return other
		elif other.match(self.glob):
			if self.negate == other.negate:
				return self
		return None

	def __eq__(self, other):
		try:
			return self.glob == other.glob and self.negate == other.negate and self.flags == other.flags
		except AttributeError:
			return False

	def __str__(self):
		if self.negate:
			return "not "+self.glob+"*"
		return self.glob+"*"


class EqualityMatch(base):
	"""Equality restriction- match if the stored value equals the passed in value"""

	__slots__ = ("val", "negate")
	def __init__(self, val, negate=False):
		self.val, self.negate = val, negate

	def match(self, actual_val):
		return (self.val == actual_val) != self.negate

	def __hash__(self):
		return hash((self.val, self.negate))

	def __eq__(self, other):
		try:
			return self.val == other.val and self.negate == other.negate
		except AttributeError:
			return False


class ContainmentMatch(base):

	"""used for an 'in' style operation, 'x86' in ['x86','~x86'] for example
	note that negation of this *does* not result in a true NAND when all is on."""

	__slots__ = ("vals", "all")

	__inst_caching__ = True

	def __init__(self, *vals, **kwds):
		"""vals must support a contaiment test
		if all is set to True, all vals must match"""

		self.all = bool(kwds.pop("all", False))
		super(ContainmentMatch, self).__init__(**kwds)
		# note that we're discarding any specialized __getitem__ on vals here.
		# this isn't optimal, and should be special cased for known types (lists/tuples fex)
		self.vals = frozenset(vals)

	def match(self, val):
		if isinstance(val, (str, unicode)):
			return (val in self.vals) ^ self.negate

		# this can, and should be optimized to do len checks- iterate over the smaller of the two
		# see above about special casing bits.  need the same protection here, on the offchance
		# (as contents sets do), the __getitem__ is non standard.
		if self.all:
			return bool(self.vals.difference(val)) == self.negate
		return any(True for x in self.vals if x in val) != self.negate

	def force_False(self, pkg, attr, val):

		# XXX pretty much positive this isn't working.
		if isinstance(val, (str, unicode)):
			# unchangable
			if self.all:
				if len(self.vals) != 1:
					yield False
				else:
					yield (self.vals[0] in val) ^ self.negate
			else:
				yield (val in self.vals) ^ self.negate
			return

		entry = pkg.changes_count()
		if self.negate:
			if self.all:
				def filter(truths):		return False in truths
				def true(r, pvals):		return pkg.request_enable(attr, r)
				def false(r, pvals):	return pkg.request_disable(attr, r)

				truths = [x in val for x in self.vals]

				for x in boolean.iterative_quad_toggling(pkg, None, list(self.vals), 0, len(self.vals), truths, filter,
					desired_false=false, desired_true=true):
					yield True
			else:
				if pkg.request_disable(attr, *self.vals):
					yield True
			return

		if not self.all:
			if pkg.request_disable(attr, *self.vals):
				yield True
		else:
			l = len(self.vals)
			def filter(truths):		return truths.count(True) < l
			def true(r, pvals):		return pkg.request_enable(attr, r)
			def false(r, pvals):	return pkg.request_disable(attr, r)
			truths = [x in val for x in self.vals]
			for x in boolean.iterative_quad_toggling(pkg, None, list(self.vals), 0, l, truths, filter,
				desired_false=false, desired_true=true):
				yield True
		return


	def force_True(self, pkg, attr, val):

		# XXX pretty much positive this isn't working.

		if isinstance(val, (str, unicode)):
			# unchangable
			if self.all:
				if len(self.vals) != 1:
					return False
				else:
					return (self.vals[0] in val) ^ self.negate
			else:
				return (val in self.vals) ^ self.negate
			return False

		entry = pkg.changes_count()
		if not self.negate:
			if not self.all:
				def filter(truths):
					return True in truths
				def true(r, pvals):
					return pkg.request_enable(attr, r)
				def false(r, pvals):
					return pkg.request_disable(attr, r)

				truths = [x in val for x in self.vals]

				for x in boolean.iterative_quad_toggling(pkg, None, list(self.vals), 0, len(self.vals), truths, filter,
					desired_false=false, desired_true=true):
					return True
			else:
				if pkg.request_enable(attr, *self.vals):
					return True
			return False

		# negation
		if not self.all:
			if pkg.request_disable(attr, *self.vals):
				return True
		else:
			def filter(truths):		return True not in truths
			def true(r, pvals):		return pkg.request_enable(attr, r)
			def false(r, pvals):	return pkg.request_disable(attr, r)
			truths = [x in val for x in self.vals]
			for x in boolean.iterative_quad_toggling(pkg, None, list(self.vals), 0, len(self.vals), truths, filter,
				desired_false=false, desired_true=true):
				return True
		return False


	def __eq__(self, other):
		try:
			return self.all == other.all and self.negate == other.negate and self.vals == other.vals
		except AttributeError:
			return False
	
	def __str__(self):
		if self.negate:
			s = "not contains [%s]"
		else:
			s = "contains [%s]"
		return s % ', '.join(map(str, self.vals))

for m, l in [[boolean, ["AndRestriction", "OrRestriction", "XorRestriction"]], \
	[restriction, ["AlwaysBool"]]]:
	for x in l:
		o = getattr(m, x)
		doc = o.__doc__
		o = pre_curry(o, node_type=value_type)
		if doc == None:
			doc = ''
		else:
			# do this so indentation on pydoc __doc__ is sane
			doc = "\n".join(x.lstrip() for x in doc.split("\n")) + "\n"
			doc += "Automatically set to package type"
		globals()[x] = pretty_docs(o, doc)

del x, m, l, o, doc

AlwaysTrue = AlwaysBool(negate=True)
AlwaysFalse = AlwaysBool(negate=False)

