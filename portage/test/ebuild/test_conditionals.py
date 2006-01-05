# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id:$

import os
from itertools import imap
from twisted.trial import unittest

from portage.package.atom import atom
from portage.ebuild.conditionals import DepSet
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

class DepSetTest(unittest.TestCase):

	depstring_input={"AndRestriction":"|| ( ( x11-libs/libXrender x11-libs/libX11 x11-libs/libXt ) virtual/x11 )"}

	def depset_consistency_check(self, depstring):
		norm_depstring = normalize_depstring(depstring)
		d = DepSet(
			norm_depstring, atom,
			operators={"":AndRestriction,"||":OrRestriction})
		output_depstring = str(d)
		self.assertEquals(norm_depstring, output_depstring)

	def test_depstrings(self):
		for k in self.depstring_input:
			self.depset_consistency_check(self.depstring_input[k])
