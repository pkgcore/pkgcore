# Copyright: 2005 Zac Medico <zmedico@gentoo.org>
# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2

import os
from itertools import imap
from twisted.trial import unittest

from pkgcore.ebuild.conditionals import DepSet, ParseError
from pkgcore.restrictions import boolean, packages
from pkgcore.util.currying import post_curry
from pkgcore.util.iterables import expandable_chain
from pkgcore.util.lists import iter_flatten

def gen_depset(s):
	return DepSet(s, str, operators={"||":boolean.OrRestriction, "":boolean.AndRestriction})

class DepSetTest(unittest.TestCase):

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
		locals()["test ParseError '%s'" % x] = post_curry(t, x)
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

	def check(self, s):
		if isinstance(s, (list, tuple)):
			s,v = s[:]
			v = list(v)
			for idx, x in enumerate(v):
				if isinstance(x, (list, tuple)):
					v[idx] = set(x)
		else:
			v = s.split()
		self.assertEqual(list(self.flatten_restricts(gen_depset(s))), list(v))

	for s in [
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

		( "x? ( a y? ( || ( b c ) d ) e ) f1 f? ( g h ) i", 
			(
			["x"], "(", "a", ["x", "y"], "(", "||", "(", "b", 
			"c", ")", "d", ")", "e", ")", "f1",
			["f"], "(", "g", "h", ")", "i"
			)
		)]:
		
		if isinstance(s, basestring):
			locals()["test '%s'" % s] = post_curry(check, s)
		else:
			locals()["test '%s'" % s[0]] = post_curry(check, s)
			
	def test_and_parsing(self):
		self.assertEqual(("a", "b", "c"), gen_depset("( a b c )").restrictions[0].restrictions)
