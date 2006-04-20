# Copyright: 2005 Brian Harring <ferringb@gentoo.org>
# License: GPL2

import os
from itertools import imap
from twisted.trial import unittest

from pkgcore.ebuild.conditionals import DepSet, ParseError
from pkgcore.restrictions import boolean, packages
from pkgcore.util.currying import post_curry
from pkgcore.util.iterables import expandable_chain
from pkgcore.util.lists import iter_flatten

def gen_depset(s, operators=None):
	if operators is None:
		operators = {"":boolean.AndRestriction, "||":boolean.OrRestriction}
	return DepSet(s, str, operators=operators)

class DepSetParsingTest(unittest.TestCase):

	def t(self, s):
		self.assertRaises(ParseError, gen_depset, s)
	
	for x in ("( )", "( a b c", "(a b c )", 
		"( a b c)", "()", "x?( a )", 
		"?x (a)", "x? (a )", "x? ( a b)", 
		"x? ( x? () )", "x? ( x? (a)", "(", ")",
		"||(", "||()", "||( )", "|| ()", 
		"|| (", "|| )", "||)",	"|| ( x? ( )", 
		"|| ( x?() )", "|| (x )", "|| ( x)",
		"a|", "a?", "a?b", "a||b", 
		"a(", "a)b", "x? y", "( x )?", "||?"):
		locals()["test assert ParseError '%s'" % x] = post_curry(t, x)
	del x

	@staticmethod
	def mangle_cond_payload(p):
		l = [p]
		if isinstance(p, boolean.AndRestriction):
			l = iter(p)
		for x in l:
			s = ""
			if x.negate:
				s = "!"
			for y in x.vals:
				yield s + y
			
	
	def flatten_restricts(self, v):
		i = expandable_chain(v)
		depth = 0
		conditionals = []
		for x in i:
			for t,s in ((boolean.OrRestriction, "||"), (boolean.AndRestriction, "&&")):
				if isinstance(x, t):
					yield s
					yield "("
					i.appendleft(")")
					i.appendleft(x.restrictions)
					depth += 1
					break
			else:
				if isinstance(x, packages.Conditional):
					self.assertTrue(x.attr == "use")
					conditionals.insert(depth, list(self.mangle_cond_payload(x.restriction)))
					yield set(iter_flatten(conditionals[:depth + 1]))
					yield "("
					i.appendleft(")")
					i.appendleft(x.payload)
					depth += 1
				else:
					if x == ")":
						self.assertTrue(depth)
						depth -= 1
					yield x
		self.assertFalse(depth)

	def check(self, s, func=gen_depset):
		if isinstance(s, (list, tuple)):
			s,v = s[:]
			v = list(v)
			for idx, x in enumerate(v):
				if isinstance(x, (list, tuple)):
					v[idx] = set(x)
		else:
			v = s.split()
		self.assertEqual(list(self.flatten_restricts(func(s))), list(v))

	for x in [
		"a b", 
		( "", 	[]),

		( "( a b )",	("&&", "(", "a", "b", ")")),

		"|| ( a b )", 

		( "a || ( a ( b ) c || ( d ) )",
			["a", "||", "(", "a", "&&", "(", "b", ")", "c",
			"||", "(", "d", ")", ")"]),
			
		( "x? ( a b )", 
			(["x"], "(", "a", "b", ")")),

		# at some point, this should collapse it
		( "x? ( y? ( a ) )", 
			(["x"], "(", ["y", "x"], "(", "a", ")", ")")),

		# at some point, this should collapse it
		"|| ( || ( a b ) )",

		# at some point, this should collapse it
		"|| ( || ( a b ) c )",

		( "x? ( a !y? ( || ( b c ) d ) e ) f1 f? ( g h ) i", 
			(
			["x"], "(", "a", ["x", "!y"], "(", "||", "(", "b", 
			"c", ")", "d", ")", "e", ")", "f1",
			["f"], "(", "g", "h", ")", "i"
			)
		)]:
		
		if isinstance(x, basestring):
			locals()["test '%s'" % x] = post_curry(check, x)
		else:
			locals()["test '%s'" % x[0]] = post_curry(check, x)

	def test_disabling_or(self):
		self.assertRaises(ParseError, gen_depset, "|| ( a b )",
			{"operators":{"":boolean.AndRestriction}})


class DepSetConditionalsInspectionTest(unittest.TestCase):

	def test_sanity_has_conditionals(self):
		self.assertFalse(bool(gen_depset("a b").has_conditionals))
		self.assertFalse(bool(gen_depset("( a b ) || ( c d )").has_conditionals))
		self.assertTrue(bool(gen_depset("x? ( a )").has_conditionals))
		self.assertTrue(bool(gen_depset("( x? ( a ) )").has_conditionals))

#	def test_node_conds(self):
		
