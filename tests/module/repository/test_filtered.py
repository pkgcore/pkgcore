from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.cpv import VersionedCPV
from pkgcore.repository import filtered
from pkgcore.restrictions import packages, values
from pkgcore.repository.util import SimpleTree
from snakeoil.test import TestCase


class TestVisibility(TestCase):

    def setup_repos(self, restrictions=None):
        repo = SimpleTree({
            "dev-util": {"diffball": ["1.0", "0.7"], "bsdiff": ["0.4.1", "0.4.2"]},
            "dev-lib": {"fake": ["1.0", "1.0-r1"]}})
        if restrictions is None:
            restrictions = atom("dev-util/diffball")
        vrepo = filtered.tree(repo, restrictions)
        return repo, vrepo

    def test_filtering(self):
        repo, vrepo = self.setup_repos()
        a = atom("dev-lib/fake")
        a2 = atom("dev-util/diffball")
        self.assertEqual(
            sorted(vrepo.itermatch(a)), sorted(repo.itermatch(a)))
        self.assertEqual(sorted(vrepo.itermatch(a2)), sorted([]))
        repo, vrepo = self.setup_repos(atom("=dev-util/diffball-1.0"))
        self.assertEqual(
            sorted(vrepo.itermatch(a)), sorted(repo.itermatch(a)))
        self.assertEqual(
            sorted(vrepo.itermatch(a2)),
            sorted([VersionedCPV("dev-util/diffball-0.7")]))
        repo, vrepo = self.setup_repos(packages.PackageRestriction(
            "package", values.OrRestriction(
                *[values.StrExactMatch(x) for x in ("diffball", "fake")])))
        self.assertEqual(
            sorted(vrepo.itermatch(packages.AlwaysTrue)),
            sorted(repo.itermatch(atom("dev-util/bsdiff"))))

        # check sentinel value handling.
        vrepo = filtered.tree(repo, a2, sentinel_val=True)
        self.assertEqual(
            sorted(x.cpvstr for x in vrepo),
            sorted(['dev-util/diffball-0.7', 'dev-util/diffball-1.0']))

    def test_iter(self):
        repo, vrepo = self.setup_repos(packages.PackageRestriction(
            "package", values.OrRestriction(
                *[values.StrExactMatch(x) for x in ("diffball", "fake")])))
        self.assertEqual(
            sorted(vrepo), sorted(repo.itermatch(atom("dev-util/bsdiff"))))
