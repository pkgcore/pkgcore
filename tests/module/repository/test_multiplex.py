from collections import OrderedDict
from functools import partial

from pkgcore.repository.multiplex import tree
from pkgcore.repository.util import SimpleTree
from pkgcore.restrictions import packages, values

rev_sorted = partial(sorted, reverse=True)


class TestMultiplex:

    kls = staticmethod(tree)
    tree1_pkgs = (
        ("dev-util/diffball", ["1.0", "0.7"]),
        ("dev-lib/fake", ["1.0", "1.0-r1"]))
    tree2_pkgs = (
        ("dev-util/diffball", ["1.0", "1.1"]),
        ("dev-lib/bsdiff", ["1.0", "2.0"]))
    tree1_list = [f"{k}-{ver}" for k, v in tree1_pkgs for ver in v]
    tree2_list = [f"{k}-{ver}" for k, v in tree2_pkgs for ver in v]

    def setup_method(self):
        self.d1, self.d2 = {}, {}
        for key, ver in self.tree1_pkgs:
            cat, pkg = key.rsplit("/", 1)
            self.d1.setdefault(cat, {}).setdefault(pkg, []).extend(ver)
        for key, ver in self.tree2_pkgs:
            cat, pkg = key.rsplit("/", 1)
            self.d2.setdefault(cat, {}).setdefault(pkg, []).extend(ver)

        self.d1 = OrderedDict(
            (k, OrderedDict(self.d1[k].items()))
            for k in sorted(self.d1, reverse=True))
        self.d2 = OrderedDict(
            (k, OrderedDict(self.d2[k].items()))
            for k in sorted(self.d2, reverse=True))
        self.tree1 = SimpleTree(self.d1)
        self.tree2 = SimpleTree(self.d2)
        self.ctree = self.kls(self.tree1, self.tree2)

    def test_iter(self):
        assert sorted(x.cpvstr for x in self.ctree) == \
            sorted(self.tree1_list + self.tree2_list)

    def test_itermatch(self):
        imatch = self.ctree.itermatch
        assert sorted(x.cpvstr for x in imatch(packages.AlwaysTrue)) == \
            sorted(self.tree1_list + self.tree2_list)
        p = packages.PackageRestriction("package", values.StrExactMatch("diffball"))
        assert sorted(x.cpvstr for x in imatch(p)) == \
            [y for y in sorted(self.tree1_list + self.tree2_list) if "/diffball" in y]

    def test_sorting(self):
        assert list(x.cpvstr for x in self.ctree.itermatch(packages.AlwaysTrue, sorter=rev_sorted)) == \
            rev_sorted(self.tree1_list + self.tree2_list)
