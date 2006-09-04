# Copyright: 2005 Brian Harring <ferringb@gentoo.org>
# License: GPL2

from twisted.trial import unittest

from pkgcore.ebuild.conditionals import DepSet, ParseError
from pkgcore.restrictions import boolean, packages
from pkgcore.util.currying import post_curry
from pkgcore.util.iterables import expandable_chain
from pkgcore.util.lists import iflatten_instance

def gen_depset(s, operators=None, func=None):
	if func is not None:
		kwds = {"element_func":func}
	else:
		kwds = {}
	if operators is None:
		operators = {"":boolean.AndRestriction, "||":boolean.OrRestriction}
	return DepSet(s, str, operators=operators, **kwds)

class DepSetParsingTest(unittest.TestCase):

	# generate a lot of parse error assertions.
	for x in ("( )", "( a b c", "(a b c )",
		"( a b c)", "()", "x?( a )",
		"?x (a)", "x? (a )", "x? (a)", "x? ( a b)",
		"x? ( x? () )", "x? ( x? (a)", "(", ")",
		"||(", "||()", "||( )", "|| ()",
		"|| (", "|| )", "||)",	"|| ( x? ( )",
		"|| ( x?() )", "|| (x )", "|| ( x)",
		"a|", "a?", "a(b", "a)", "a||b",
		"a(", "a)b", "x? y", "( x )?", "||?"):
		locals()["test assert ParseError '%s'" % x] = post_curry(
			unittest.TestCase.assertRaises, ParseError, gen_depset, x)
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
			for t, s in ((boolean.OrRestriction, "||"), (boolean.AndRestriction, "&&")):
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
					yield set(iflatten_instance(conditionals[:depth + 1]))
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
			s, v = s[:]
			v = list(v)
			for idx, x in enumerate(v):
				if isinstance(x, (list, tuple)):
					v[idx] = set(x)
		else:
			v = s.split()
		self.assertEqual(list(self.flatten_restricts(func(s))), list(v))

	# generate a lot of assertions of parse results.
	# if it's a list, first arg is string, second is results, if
	# string, the results for testing are determined by splitting the string
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

	def test_element_func(self):
		self.assertEqual(
			gen_depset("asdf fdas", func=post_curry(str)).element_class,
			"".__class__)

	def test_disabling_or(self):
		self.assertRaises(
			ParseError, gen_depset, "|| ( a b )",
			{"operators":{"":boolean.AndRestriction}})


class DepSetConditionalsInspectionTest(unittest.TestCase):

	def test_sanity_has_conditionals(self):
		self.assertFalse(bool(gen_depset("a b").has_conditionals))
		self.assertFalse(bool(gen_depset("( a b ) || ( c d )").has_conditionals))
		self.assertTrue(bool(gen_depset("x? ( a )").has_conditionals))
		self.assertTrue(bool(gen_depset("( x? ( a ) )").has_conditionals))

	def flatten_cond(self, c):
		l = set()
		for x in c:
			if isinstance(x, boolean.base):
				self.assertEqual(len(x.dnf_solutions()), 1)
				f = x.dnf_solutions()[0]
			else:
				f = [x]
			t = set()
			for a in f:
				s = ""
				if a.negate:
					s = "!"
				t.update(["%s%s" % (s, y) for y in a.vals])
			l.add(frozenset(t))
		return l

	def check_conds(self, s, r, msg=None):
		nc = dict(
			(k, self.flatten_cond(v))
			for (k, v) in gen_depset(s).node_conds.iteritems())
		d = dict(r)
		for k, v in d.iteritems():
			if isinstance(v, basestring):
				d[k] = set([frozenset(v.split())])
			elif isinstance(v, (tuple, list)):
				d[k] = set(map(frozenset, v))
		self.assertEqual(nc, d, msg)

	for s in (
		("x? ( y )", {"y":"x"}),
		("x? ( y ) z? ( y )", {"y":["z", "x"]}),
		("x? ( z? ( w? ( y ) ) )", {"y":"w z x"}),
		("!x? ( y )", {"y":"!x"}),
		("!x? ( z? ( y a ) )", {"y":"!x z", "a":"!x z"}),
		("x ( y )", {}),
		("x ( y? ( z ) )", {"z":"y"}, "needs to dig down as deep as required"),
		("x y? ( x )", {}, "x isn't controlled by a conditional, shouldn't be in the list"),
		("|| ( y? ( x ) x )", {}, "x cannot be filtered down since x is accessible via non conditional path"),
		("|| ( y? ( x ) z )", {"x":"y"}),
		):
		locals()["test _node_conds %s" % s[0]] = post_curry(check_conds, *s)

