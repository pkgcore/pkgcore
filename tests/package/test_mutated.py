from functools import partial

from snakeoil.compatibility import cmp
from snakeoil.klass import inject_richcmp_methods_from_cmp
from snakeoil.test import TestCase

from pkgcore.package.base import base, dynamic_getattr_dict
from pkgcore.package.mutated import MutatedPkg


def passthru(val, self):
    return val

class FakePkg(base):

    # XXX why isn't this using existing classes?
    __slotting_intentionally_disabled__ = True

    def __init__(self, pkg, ver, data):
        base.__init__(self)
        self.pkg = pkg
        self.ver = ver
        self._get_attr = {k: partial(passthru, v) for k, v in data.items()}

    # disable protection.  don't want it here
    __setattr__ = object.__setattr__
    __getattr__ = dynamic_getattr_dict

    def __cmp__(self, other):
        return cmp(self.ver, other.ver)

    inject_richcmp_methods_from_cmp(locals())


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
