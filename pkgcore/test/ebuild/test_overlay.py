# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.ebuild.overlay_repository import OverlayRepo
from pkgcore.restrictions import packages, values
from pkgcore.test.repository import test_multiplex


class TestOverlays(test_multiplex.TestMultiplex):

    @staticmethod
    def kls(*trees):
        return OverlayRepo(trees)
    
    def test_iter(self):
        self.assertEqual(sorted(x.cpvstr for x in self.ctree),
            sorted(set(self.tree1_list + self.tree2_list)))

    def test_itermatch(self):
        imatch = self.ctree.itermatch
        self.assertEqual(
            sorted(x.cpvstr for x in imatch(packages.AlwaysTrue)),
            sorted(set(self.tree1_list + self.tree2_list)))
        p = packages.PackageRestriction("package",
            values.StrExactMatch("diffball"))
        self.assertEqual(
            sorted(x.cpvstr for x in imatch(p)),
            sorted(set(y for y in self.tree1_list + self.tree2_list
                if "/diffball" in y)))

    def test_sorting(self):
        self.assertEqual(list(x.cpvstr for x in
            self.ctree.match(packages.AlwaysTrue,
                sorter=test_multiplex.rev_sorted)),
            test_multiplex.rev_sorted(
                set(self.tree1_list + self.tree2_list)))
