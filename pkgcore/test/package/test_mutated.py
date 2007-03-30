# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase
from pkgcore.package.mutated import MutatedPkg
from pkgcore.package.base import base
from snakeoil.currying import partial

def passthru(val, self):
    return val

class FakePkg(base):

    def __init__(self, pkg, ver, data):
        base.__init__(self)
        self.pkg = pkg
        self.ver = ver
        self._get_attr = dict((k, partial(passthru, v))
            for k,v in data.iteritems())

    # disable protection.  don't want it here
    __setattr__ = object.__setattr__

    def __cmp__(self, other):
        return cmp(self.ver, other.ver)


class TestMutatedPkg(TestCase):

    def make_fakepkg(self, pkg="dar", ver=1, data=None):
        if data is None:
            data = {"a":1}
        return FakePkg(pkg, ver, data)

    def test_raw_pkg(self):
        pkg = self.make_fakepkg()
        self.assertIdentical(MutatedPkg(pkg, {})._raw_pkg, pkg)

    def test_cmp(self):
        pkg1 = self.make_fakepkg()
        pkg2 = self.make_fakepkg(ver=2)
        mpkg1 = MutatedPkg(pkg1, {})
        mpkg2 = MutatedPkg(pkg2, {})

        for lpkg in (pkg1, mpkg1):
            self.assertTrue(cmp(lpkg, mpkg2) < 0)
            self.assertTrue(cmp(mpkg2, lpkg) > 0)
        self.assertEqual(mpkg1, mpkg1)
        self.assertEqual(pkg1, mpkg1)

    def test_getattr(self):
        pkg = self.make_fakepkg()
        self.assertEqual(MutatedPkg(pkg, {}).a, 1)
        self.assertEqual(MutatedPkg(pkg, {"a":2}).a, 2)
        self.assertRaises(AttributeError, MutatedPkg(pkg, {}).__getattr__, "b")
