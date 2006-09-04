# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.restrictions import util, packages, values
from twisted.trial import unittest

class Test_collect_package_restrictions(unittest.TestCase):

	def test_collect_all(self):
		prs = [packages.PackageRestriction("category", values.AlwaysTrue)] * 10
		self.assertEqual(
			sorted(util.collect_package_restrictions(packages.AndRestriction(
						packages.OrRestriction(), packages.AndRestriction(),
						*prs))),
			sorted(prs))

	def test_collect_specific(self):
		prs = {}
		for x in ("category", "package", "version", "iuse"):
			prs[x] = packages.PackageRestriction(x, values.AlwaysTrue)

		r = packages.AndRestriction(
			packages.OrRestriction(*prs.values()), packages.AlwaysTrue)
		for k, v in prs.iteritems():
			self.assertEqual(
				sorted(util.collect_package_restrictions(r, attrs=[k])),
				sorted([v]))
		r = packages.AndRestriction(packages.OrRestriction(
				*prs.values()), *prs.values())
		for k, v in prs.iteritems():
			self.assertEqual(
				sorted(util.collect_package_restrictions(r, attrs=[k])),
				sorted([v] * 2))
