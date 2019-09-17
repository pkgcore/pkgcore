from collections import OrderedDict
from functools import partial

from snakeoil.currying import post_curry
from snakeoil.test import TestCase

from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.cpv import VersionedCPV
from pkgcore.operations.repo import operations
from pkgcore.package.mutated import MutatedPkg
from pkgcore.repository.util import SimpleTree
from pkgcore.restrictions import packages, values, boolean
from pkgcore.test import malleable_obj


class TestPrototype(TestCase):

    def setUp(self):
        # we use an OrderedDict here specifically to trigger any sorter
        # related bugs
        d = {
            "dev-util": {"diffball": ["1.0", "0.7"], "bsdiff": ["0.4.1", "0.4.2"]},
            "dev-lib": {"fake": ["1.0", "1.0-r1"]}}
        self.repo = SimpleTree(
            OrderedDict((k, d[k]) for k in sorted(d, reverse=True)))

    def test_concurrent_access(self):
        iall = iter(self.repo)
        self.repo.match(atom("dev-lib/fake"))
        pkg = next(iall)
        if pkg.category == 'dev-util':
            self.repo.match(atom("dev-lib/fake"))
        else:
            self.repo.match(atom("dev-util/diffball"))
        # should not explode...
        list(iall)

    def test_internal_lookups(self):
        self.assertEqual(
            sorted(self.repo.categories),
            sorted(["dev-lib", "dev-util"]))
        self.assertEqual(
            sorted(map("/".join, self.repo.versions)),
            sorted([x for x in ["dev-util/diffball", "dev-util/bsdiff", "dev-lib/fake"]]))
        self.assertEqual(
            sorted(
                f"{cp[0]}/{cp[1]}-{v}"
                for cp, t in self.repo.versions.items() for v in t),
            sorted([
                "dev-util/diffball-1.0", "dev-util/diffball-0.7",
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
            sorted(VersionedCPV(x) for x in (
                "dev-util/diffball-0.7", "dev-util/diffball-1.0",
                "dev-util/bsdiff-0.4.1", "dev-util/bsdiff-0.4.2")))
        self.assertEqual(
            sorted(self.repo.itermatch(packages.AndRestriction(rc, rp))),
            sorted(VersionedCPV(x) for x in (
                "dev-util/diffball-0.7", "dev-util/diffball-1.0")))
        self.assertEqual(
            sorted(self.repo),
            self.repo.match(packages.AlwaysTrue, sorter=sorted))
        # mix/match cat/pkg to check that it handles that corner case
        # properly for sorting.
        self.assertEqual(
            sorted(self.repo, reverse=True),
            self.repo.match(packages.OrRestriction(
                rc, rp, packages.AlwaysTrue),
                sorter=partial(sorted, reverse=True)))
        rc2 = packages.PackageRestriction(
            "category", values.StrExactMatch("dev-lib"))
        self.assertEqual(
            sorted(self.repo.itermatch(packages.AndRestriction(rp, rc2))),
            sorted([]))

        # note this mixes a category level match, and a pkg level
        # match. they *must* be treated as an or.
        self.assertEqual(
            sorted(self.repo.itermatch(packages.OrRestriction(rp, rc2))),
            sorted(VersionedCPV(x) for x in (
                "dev-util/diffball-0.7", "dev-util/diffball-1.0",
                "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))

        # this is similar to the test above, but mixes a cat/pkg
        # candidate with a pkg candidate
        rp2 = packages.PackageRestriction(
            "package", values.StrExactMatch("fake"))
        r = packages.OrRestriction(atom("dev-util/diffball"), rp2)
        self.assertEqual(
            sorted(self.repo.itermatch(r)),
            sorted(VersionedCPV(x) for x in (
                "dev-util/diffball-0.7", "dev-util/diffball-1.0",
                "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))

        self.assertEqual(
            sorted(self.repo.itermatch(
                packages.OrRestriction(packages.AlwaysTrue, rp2))),
            sorted(VersionedCPV(x) for x in (
                "dev-util/diffball-0.7", "dev-util/diffball-1.0",
                "dev-util/bsdiff-0.4.1", "dev-util/bsdiff-0.4.2",
                "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))

        self.assertEqual(
            sorted(self.repo.itermatch(
                packages.PackageRestriction(
                    'category', values.StrExactMatch('dev-util', negate=True)))),
            sorted(VersionedCPV(x) for x in ("dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))

        obj = malleable_obj(livefs=False)
        pkg_cls = post_curry(MutatedPkg, {'repo': obj})
        self.assertEqual(
            sorted(self.repo.itermatch(
                boolean.AndRestriction(
                    boolean.OrRestriction(
                        packages.PackageRestriction(
                            "repo.livefs", values.EqualityMatch(False)),
                        packages.PackageRestriction(
                            "category", values.StrExactMatch("virtual"))),
                    atom("dev-lib/fake")),
                pkg_cls=pkg_cls)),
            sorted(VersionedCPV(x) for x in (
                "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))

        self.assertEqual(
            sorted(self.repo.itermatch(
                packages.PackageRestriction(
                    'category', values.StrExactMatch('dev-lib', negate=True),
                    negate=True))),
            sorted(VersionedCPV(x) for x in (
                "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))

        self.assertEqual(
            sorted(self.repo.itermatch(
                packages.PackageRestriction(
                    'category', values.StrExactMatch('dev-lib', negate=True),
                    negate=True))),
            sorted(VersionedCPV(x) for x in (
                "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))

    def test_iter(self):
        self.assertEqual(
            sorted(self.repo),
            sorted(VersionedCPV(x) for x in (
                "dev-util/diffball-1.0", "dev-util/diffball-0.7",
                "dev-util/bsdiff-0.4.1", "dev-util/bsdiff-0.4.2",
                "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))

    def test_notify_remove(self):
        pkg = VersionedCPV("dev-util/diffball-1.0")
        self.repo.notify_remove_package(pkg)
        self.assertEqual(list(self.repo.versions[
            (pkg.category, pkg.package)]), ["0.7"])

        # test version being emptied, and package updated
        pkg = VersionedCPV("dev-util/diffball-0.7")
        self.repo.notify_remove_package(pkg)
        self.assertNotIn((pkg.category, pkg.package), self.repo.versions)
        self.assertNotIn(pkg.package, self.repo.packages[pkg.category])

        # test no remaining packages, category updated
        pkg = VersionedCPV("dev-util/bsdiff-0.4.1")
        self.repo.notify_remove_package(pkg)

        pkg = VersionedCPV("dev-util/bsdiff-0.4.2")
        self.repo.notify_remove_package(pkg)
        self.assertNotIn((pkg.category, pkg.package), self.repo.versions)
        self.assertNotIn(pkg.category, self.repo.packages)
        self.assertNotIn(pkg.category, self.repo.categories)

    def test_notify_add(self):
        pkg = VersionedCPV("dev-util/diffball-1.2")
        self.repo.notify_add_package(pkg)
        self.assertEqual(sorted(self.repo.versions[
            (pkg.category, pkg.package)]), sorted(["1.0", "1.2", "0.7"]))

        pkg = VersionedCPV("foo/bar-1.0")
        self.repo.notify_add_package(pkg)
        self.assertIn(pkg.category, self.repo.categories)
        self.assertIn(pkg.category, self.repo.packages)
        ver_key = (pkg.category, pkg.package)
        self.assertIn(ver_key, self.repo.versions)
        self.assertEqual(list(self.repo.versions[ver_key]), ["1.0"])

        pkg = VersionedCPV("foo/cows-1.0")
        self.repo.notify_add_package(pkg)
        self.assertIn((pkg.category, pkg.package), self.repo.versions)

    def _simple_redirect_test(self, attr, arg1='=dev-util/diffball-1.0', arg2=None):
        l = []
        uniq_obj = object()

        def f(*a, **kw):
            a = a[1:-1]
            l.extend((a, kw))
            return uniq_obj
        # if replace, override _replace since replace reflects to it

        class my_ops(operations):
            locals()[f'_cmd_implementation_{attr}'] = f
        self.repo.operations_kls = my_ops
        args = [self.repo.match(atom(arg1))]
        if arg2:
            args.append(VersionedCPV(arg2))
        self.repo.frozen = False
        op = getattr(self.repo.operations, attr)

        def simple_check(op, args, **kw):
            l[:] = []
            self.assertEqual(op(*args, **kw), uniq_obj)
            self.assertEqual(len(l), 2)
            self.assertEqual(list(l[0]), args)
            self.assertTrue(l)

        self.assertTrue(self.repo.operations.supports(attr))
        simple_check(op, args)
        self.assertFalse(l[1])
        simple_check(op, args)
        self.assertNotIn('force', l[1])
        self.repo.frozen = True
        self.assertFalse(self.repo.operations.supports(attr))
        self.assertFalse(hasattr(self.repo.operations, attr))

    test_replace = post_curry(_simple_redirect_test, 'replace', arg2='dev-util/diffball-1.1')
    test_uninstall = post_curry(_simple_redirect_test, 'uninstall')
    test_install = post_curry(_simple_redirect_test, 'install')
