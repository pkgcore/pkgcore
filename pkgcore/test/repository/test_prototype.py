# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase
from snakeoil.mappings import OrderedDict

from pkgcore.restrictions import packages, values
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.cpv import CPV
from pkgcore.repository.util import SimpleTree

class TestPrototype(TestCase):

    def setUp(self):
        # we an orderreddict here specifically to trigger any sorter
        # related bugs
        d = {"dev-util":{
                "diffball":["1.0", "0.7"], "bsdiff":["0.4.1", "0.4.2"]},
            "dev-lib":{"fake":["1.0", "1.0-r1"]}}
        self.repo = SimpleTree(
            OrderedDict((k, d[k]) for k in sorted(d, reverse=True)))

    def test_internal_lookups(self):
        self.assertEqual(
            sorted(self.repo.categories),
            sorted(["dev-lib", "dev-util"]))
        self.assertEqual(
            sorted(map("/".join, self.repo.versions)),
                sorted([x for x in
                ["dev-util/diffball", "dev-util/bsdiff", "dev-lib/fake"]]))
        self.assertEqual(
            sorted("%s/%s-%s" % (cp[0], cp[1], v)
                for cp, t in self.repo.versions.iteritems() for v in t),
            sorted(["dev-util/diffball-1.0", "dev-util/diffball-0.7",
                    "dev-util/bsdiff-0.4.1", "dev-util/bsdiff-0.4.2",
                    "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1"]))

    def test_simple_query(self):
        a = atom("=dev-util/diffball-1.0")
        self.repo.match(a)
        self.assertTrue(self.repo.match(a))
        self.assertFalse(self.repo.match(atom("dev-util/monkeys_rule")))

    def test_identify_candidates(self):
        self.assertRaises(TypeError, self.repo.match, ("asdf"))
        rc = packages.PackageRestriction(
            "category", values.StrExactMatch("dev-util"))
        self.assertEqual(
            sorted(set(x.package for x in self.repo.itermatch(rc))),
            sorted(["diffball", "bsdiff"]))
        rp = packages.PackageRestriction(
            "package", values.StrExactMatch("diffball"))
        self.assertEqual(
            list(x.version for x in self.repo.itermatch(rp, sorter=sorted)),
            ["0.7", "1.0"])
        self.assertEqual(
            self.repo.match(packages.OrRestriction(rc, rp), sorter=sorted),
            sorted(CPV(x) for x in (
                    "dev-util/diffball-0.7", "dev-util/diffball-1.0",
                    "dev-util/bsdiff-0.4.1", "dev-util/bsdiff-0.4.2")))
        self.assertEqual(
            sorted(self.repo.itermatch(packages.AndRestriction(rc, rp))),
            sorted(CPV(x) for x in (
                    "dev-util/diffball-0.7", "dev-util/diffball-1.0")))
        self.assertEqual(
            sorted(self.repo),
            self.repo.match(packages.AlwaysTrue, sorter=sorted))
        # mix/match cat/pkg to check that it handles that corner case
        # properly for sorting.
        self.assertEqual(
            sorted(self.repo),
            self.repo.match(packages.OrRestriction(
                    rc, rp, packages.AlwaysTrue), sorter=sorted))
        rc2 = packages.PackageRestriction(
            "category", values.StrExactMatch("dev-lib"))
        self.assertEqual(
            sorted(self.repo.itermatch(packages.AndRestriction(rp, rc2))),
            sorted([]))

        # note this mixes a category level match, and a pkg level
        # match. they *must* be treated as an or.
        self.assertEqual(
            sorted(self.repo.itermatch(packages.OrRestriction(rp, rc2))),
            sorted(CPV(x) for x in (
                    "dev-util/diffball-0.7", "dev-util/diffball-1.0",
                    "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))

        # this is similar to the test above, but mixes a cat/pkg
        # candidate with a pkg candidate
        rp2 = packages.PackageRestriction(
            "package", values.StrExactMatch("fake"))
        r = packages.OrRestriction(atom("dev-util/diffball"), rp2)
        self.assertEqual(sorted(self.repo.itermatch(r)),
            sorted(CPV(x) for x in (
                    "dev-util/diffball-0.7", "dev-util/diffball-1.0",
                    "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))

        self.assertEqual(
            sorted(self.repo.itermatch(
                    packages.OrRestriction(packages.AlwaysTrue, rp2))),
            sorted(CPV(x) for x in (
                    "dev-util/diffball-0.7", "dev-util/diffball-1.0",
                    "dev-util/bsdiff-0.4.1", "dev-util/bsdiff-0.4.2",
                    "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))


    def test_iter(self):
        self.assertEqual(
            sorted(self.repo),
            sorted(CPV(x) for x in (
                    "dev-util/diffball-1.0", "dev-util/diffball-0.7",
                    "dev-util/bsdiff-0.4.1", "dev-util/bsdiff-0.4.2",
                    "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))

    def test_notify_remove(self):
        pkg = CPV("dev-util/diffball-1.0")
        self.repo.notify_remove_package(pkg)
        self.assertEqual(list(self.repo.versions[
            (pkg.category, pkg.package)]), ["0.7"])

        # test version being emptied, and package updated
        pkg = CPV("dev-util/diffball-0.7")
        self.repo.notify_remove_package(pkg)
        self.assertNotIn((pkg.category, pkg.package), self.repo.versions)
        self.assertNotIn(pkg.package, self.repo.packages[pkg.category])

        # test no remaining packages, category updated
        pkg = CPV("dev-util/bsdiff-0.4.1")
        self.repo.notify_remove_package(pkg)

        pkg = CPV("dev-util/bsdiff-0.4.2")
        self.repo.notify_remove_package(pkg)
        self.assertNotIn((pkg.category, pkg.package), self.repo.versions)
        self.assertNotIn(pkg.category, self.repo.packages)
        self.assertNotIn(pkg.category, self.repo.categories)

    def test_notify_add(self):
        pkg = CPV("dev-util/diffball-1.2")
        self.repo.notify_add_package(pkg)
        self.assertEqual(sorted(self.repo.versions[
            (pkg.category, pkg.package)]), sorted(["1.0", "1.2", "0.7"]))

        pkg = CPV("foo/bar-1.0")
        self.repo.notify_add_package(pkg)
        self.assertIn(pkg.category, self.repo.categories)
        self.assertIn(pkg.category, self.repo.packages)
        ver_key = (pkg.category, pkg.package)
        self.assertIn(ver_key, self.repo.versions)
        self.assertEqual(list(self.repo.versions[ver_key]), ["1.0"])

        pkg = CPV("foo/cows-1.0")
        self.repo.notify_add_package(pkg)
        self.assertIn((pkg.category, pkg.package), self.repo.versions)
