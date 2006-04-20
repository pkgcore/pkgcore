# Copyright: 2005 Zac Medico <zmedico@gentoo.org>
# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2

import os
from itertools import imap
from twisted.trial import unittest

from pkgcore.ebuild.conditionals import DepSet, ParseError
from pkgcore.restrictions import boolean
from pkgcore.util.currying import post_curry
from pkgcore.util.lists import iter_flatten

def get_depset(s):
	return DepSet(s, str, operators={"||":boolean.OrRestriction, "":boolean.AndRestriction})

class DepSetTest(unittest.TestCase):

	def t(self, s):
		self.assertRaises(ParseError, get_depset, s)
	
	for x in ("( )", "( a b c", "(a b c )", "( a b c)", "()",
		"x?( a )", "?x (a)", "x? (a )", "x? ( a b)", 
		"x? ( x? () )", "x? ( x? (a)", "(", ")", 
		"||(", "||()", "||( )", "|| ()", "|| (", "|| )", "||)",
		"|| ( x? ( )", "|| ( x?() )", "|| (x )", "|| ( x)",
		"a|", "a?", "a?b", "a||b", "a(", "a)b"):
		locals()["test ParseError '%s'" % x] = post_curry(t, x)
	del x

#	def t2(self, s, v):
#		self.assertEquals(iter_flatten(get_depset(s)), tuple(iter_flatten(v)))

	def test_and_parsing(self):
		self.assertEqual(("a", "b", "c"), get_depset("( a b c )").restrictions[0].restrictions)
