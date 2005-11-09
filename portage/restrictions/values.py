# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: values.py 2282 2005-11-10 00:30:30Z ferringb $

import re, logging
from portage.restrictions import restriction, boolean
from portage.util.currying import pre_curry, pretty_docs

value_type = "values"

class base(restriction.base):
	"""base restriction matching object; overrides setattr to provide the usual write once trickery
	all derivatives *must* be __slot__ based"""

	__slots__ = restriction.base.__slots__
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
	pass


class StrMatch(base):
	""" Base string matching restriction.  all derivatives must be __slot__ based classes"""
	__slots__ = ["flags"] + base.__slots__
	pass


class StrRegexMatch(StrMatch):
	#potentially redesign this to jit the compiled_re object
	__slots__ = tuple(["regex", "compiled_re"] + StrMatch.__slots__)

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
	__slots__ = tuple(["exact", "flags"] + StrMatch.__slots__)

	def __init__(self, exact, CaseSensitive=True, **kwds):
		super(StrExactMatch, self).__init__(**kwds)
		if not CaseSensitive:
			self.flags = re.I
			self.exact = str(exact).lower()
		else:
			self.flags = 0
			self.exact = str(exact)

	def match(self, value):
		if self.flags & re.I:	return (self.exact == str(value).lower()) ^ self.negate
		else:			return (self.exact == str(value)) ^ self.negate

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
		if self.negate:	return "!= "+self.exact
		return "== "+self.exact


class StrGlobMatch(StrMatch):

	__slots__ = tuple(["glob", "prefix"] + StrMatch.__slots__)

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
		return self.glob == other.glob and self.negate == other.negate and self.flags == other.flags

	def __str__(self):
		if self.negate:	return "not "+self.glob+"*"
		return self.glob+"*"


class ContainmentMatch(base):

	"""used for an 'in' style operation, 'x86' in ['x86','~x86'] for example
	note that negation of this *does* not result in a true NAND when all is on."""

	__slots__ = tuple(["vals", "vals_len", "all"] + base.__slots__)
	
	def __init__(self, *vals, **kwds):
		"""vals must support a contaiment test
		if all is set to True, all vals must match"""

		if "all" in kwds:
			self.all = kwds["all"]
			del kwds["all"]
		else:
			self.all = False
		super(ContainmentMatch, self).__init__(**kwds)
		self.vals = set(vals)
		self.vals_len = len(self.vals)
		
	def match(self, val):
		if isinstance(val, (str, unicode)):
			return val in self.vals ^ self.negate
		rem = set(self.vals)
		try:
			# assume our lookup is faster, since we don't know if val is constant lookup or not
			for x in val:
				if x in rem:
					if self.all:
						rem.remove(x)
						if len(rem) == 0:
							return not self.negate
					else:
						return not self.negate
			return self.negate
		except TypeError:
			return self.negate
#			return val in self.vals ^ self.negate

	def force_False(self, pkg, attr, val):
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
			truths=[x in val for x in self.vals]
			for x in boolean.iterative_quad_toggling(pkg, None, list(self.vals), 0, l, truths, filter, 
				desired_false=false, desired_true=true):
				yield True
			
		return


	def force_True(self, pkg, attr, val):
		import pdb;pdb.set_trace()
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
		if not self.negate:
			if not self.all:
				def filter(truths):		return True in truths
				def true(r, pvals):		return pkg.request_enable(attr, r)
				def false(r, pvals):	return pkg.request_disable(attr, r)

				truths = [x in val for x in self.vals]
				
				for x in boolean.iterative_quad_toggling(pkg, None, list(self.vals), 0, len(self.vals), truths, filter, 
					desired_false=false, desired_true=true):
					yield True
			else:
				if pkg.request_enable(attr, *self.vals):
					yield True
			return

		# negation
		if not self.all:
			if pkg.request_disable(attr, *self.vals):
				yield True
		else:
			def filter(truths):		return True not in truths
			def true(r, pvals):		return pkg.request_enable(attr, r)
			def false(r, pvals):	return pkg.request_disable(attr, r)
			truths=[x in val for x in self.vals]
			for x in boolean.iterative_quad_toggling(pkg, None, list(self.vals), 0, len(self.vals), truths, filter, 
				desired_false=false, desired_true=true):
				yield True
		return


	def __str__(self):
		if self.negate:	s="not contains [%s]"
		else:			s="contains [%s]"
		return s % ', '.join(map(str, self.vals))


def get_val(pkg, attr):
	attr_list = '.'.split(attr)
	o=pkg
	try:
		for x in attr:
			o=getattr(o, x)
		return x
	except AttributeError, ae:
		logger.warn("impossible happened, unable to get attr '%s' from pkg '%s', yet it was handed into my parent" 
			% (attr, pkg))
		raise


for m, l in [[boolean, ["AndRestriction", "OrRestriction", "XorRestriction"]], \
	[restriction, ["AlwaysBool"]]]:
	for x in l:
		o = getattr(m, x)
		doc = o.__doc__
		o = pre_curry(o, value_type)
		if doc == None:
			doc = ''
		else:
			# do this so indentation on pydoc __doc__ is sane
			doc = "\n".join(map(lambda x:x.lstrip(), doc.split("\n"))) +"\n"
			doc += "Automatically set to package type"
		globals()[x] = pretty_docs(o, doc)

del x, m, l, o, doc

AlwaysTrue = AlwaysBool(True)
AlwaysFalse = AlwaysBool(True)

