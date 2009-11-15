# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.test import TestCase
from pkgcore.restrictions import util, packages, values

class Test_collect_package_restrictions(TestCase):

    def test_collect_all(self):
        prs = [packages.PackageRestriction("category", values.AlwaysTrue)] * 10
        self.assertEqual(
            list(util.collect_package_restrictions(packages.AndRestriction(
                        packages.OrRestriction(), packages.AndRestriction(),
                        *prs))),
            prs)

    def test_collect_specific(self):
        prs = {}
        for x in ("category", "package", "version", "iuse"):
            prs[x] = packages.PackageRestriction(x, values.AlwaysTrue)

        r = packages.AndRestriction(
            packages.OrRestriction(*prs.values()), packages.AlwaysTrue)
        for k, v in prs.iteritems():
            self.assertEqual(
                list(util.collect_package_restrictions(r, attrs=[k])),
                [v])
        r = packages.AndRestriction(packages.OrRestriction(
                *prs.values()), *prs.values())
        for k, v in prs.iteritems():
            self.assertEqual(
                list(util.collect_package_restrictions(r, attrs=[k])),
                [v] * 2)
