# Copyright: 2006 Zac Medico <zmedico@gentoo.org>
# License: GPL2

from twisted.trial import unittest
from portage.restrictions.values import StrExactMatch
from portage.restrictions.packages import package_type
from portage.ebuild.conditionals import DepSet
from portage.graph.state_graph import combinations
if not hasattr(__builtins__, "set"):
	from sets import Set as set

class StrPackage(StrExactMatch):
	"""simple string restriction for testing purposes (portage.package.atom requires
	categories and has many other features which would only be clutter here)"""
	def __init__(self, *args, **kwds):
		super(StrPackage, self).__init__(*args, **kwds)
		# package_type is a hard coded requirement by DepSet
		self.type = package_type

class CombinationsTest(unittest.TestCase):

	test_input = {
		"|| ( a ( b c ) )":("a","b c"),
		"|| ( ( a b ) c ( d e ) )":("a b", "c", "d e"),
		"|| ( a ( b c ) ( d e ) )":("a", "b c", "d e") ,
		"|| ( a b ) ( c d )":("a c d", "b c d"),
		"a || ( b c )":("a b","a c")
	}

	def get_combinations(self, depstring):
		d = DepSet(depstring, StrPackage)
		return combinations(d, StrPackage)

	def test_combinations(self):
		for depstring, comb_strings in self.test_input.iteritems():
			comb = self.get_combinations(depstring)
			comb_known_good = set()
			for comb_string in comb_strings:
				comb_known_good.update(self.get_combinations(comb_string))
			self.assertEquals(comb,comb_known_good)
