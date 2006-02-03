# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id:$

import os
from itertools import imap
from twisted.trial import unittest

from portage.ebuild.conditionals import DepSet
from portage.restrictions.values import StrExactMatch
from portage.restrictions import boolean
from portage.restrictions import packages
from portage.util.currying import pre_curry

def normalize_depstring(depstring):
	return " ".join(depstring.split())

class OrRestrictionOverride(boolean.OrRestriction):
	def __str__(self):
		"""We need to output standard portage depset syntax for comparison with input"""
		assert not self.negate
		return "|| ( %s )" % " ".join(imap(str, self.restrictions))

class AndRestrictionOverride(boolean.AndRestriction):
	def __str__(self):
		"""We need to output standard portage depset syntax for comparison with input"""
		assert not self.negate
		return "( %s )" % " ".join(imap(str, self.restrictions))

OrRestriction=pre_curry(OrRestrictionOverride,packages.package_type)
AndRestriction=pre_curry(AndRestrictionOverride,packages.package_type)

class StrPackage(StrExactMatch):
	"""simple string restriction for testing purposes (portage.package.atom requires
	categories and has many other features which would only be clutter here)"""
	def __init__(self, *args, **kwds):
		super(StrPackage, self).__init__(*args, **kwds)
		# package_type is a hard coded requirement by DepSet
		self.type = packages.package_type

	def __str__(self):
		assert not self.negate
		return self.exact

class DepSetTest(unittest.TestCase):

	test_input = ("|| ( ( a b ) c )",
		"|| ( a ( b c ) )",
		"|| ( ( a b ) c ( d e ) )",
		"|| ( a ( b c ) ( d e ) )",
		"|| ( a b ) ( c d )",
		"a || ( b c )")

	def depset_consistency_check(self, depstring):
		norm_depstring = normalize_depstring(depstring)
		d = DepSet(
			norm_depstring, StrPackage,
			operators={"":AndRestriction,"||":OrRestriction})
		output_depstring = str(d)
		self.assertEquals(norm_depstring, output_depstring)

	def test_depstrings(self):
		for depstring in self.test_input:
			self.depset_consistency_check(depstring)
