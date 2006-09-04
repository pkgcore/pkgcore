# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.test.repository.test_prototype import SimpleTree
from pkgcore.repository.visibility import filterTree
from pkgcore.restrictions import packages, values
from pkgcore.package.atom import atom
from pkgcore.package.cpv import CPV

class TestVisibility(unittest.TestCase):

    def setup_repos(self, restrictions=None):
        self.repo = SimpleTree({
                "dev-util":{
                    "diffball":["1.0", "0.7"], "bsdiff":["0.4.1", "0.4.2"]},
                "dev-lib":{"fake":["1.0", "1.0-r1"]}})
        if restrictions is None:
            restrictions = atom("dev-util/diffball")
        self.vrepo = filterTree(self.repo, restrictions)

    def test_filtering(self):
        self.setup_repos()
        a = atom("dev-lib/fake")
        a2 = atom("dev-util/diffball")
        self.assertEqual(
            sorted(self.vrepo.itermatch(a)), sorted(self.repo.itermatch(a)))
        self.assertEqual(sorted(self.vrepo.itermatch(a2)), sorted([]))
        self.setup_repos(atom("=dev-util/diffball-1.0"))
        self.assertEqual(
            sorted(self.vrepo.itermatch(a)), sorted(self.repo.itermatch(a)))
        self.assertEqual(
            sorted(self.vrepo.itermatch(a2)),
            sorted([CPV("dev-util/diffball-0.7")]))
        self.setup_repos(packages.PackageRestriction(
                "package", values.OrRestriction(
                    *[values.StrExactMatch(x) for x in ("diffball", "fake")])))
        self.assertEqual(
            sorted(self.vrepo.itermatch(packages.AlwaysTrue)),
            sorted(self.repo.itermatch(atom("dev-util/bsdiff"))))

    def test_iter(self):
        self.setup_repos(packages.PackageRestriction(
                "package", values.OrRestriction(
                    *[values.StrExactMatch(x) for x in ("diffball", "fake")])))
        self.assertEqual(
            sorted(self.vrepo),
            sorted(self.repo.itermatch(atom("dev-util/bsdiff"))))
