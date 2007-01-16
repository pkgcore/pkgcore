# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from pkgcore.test import TestCase
from pkgcore.restrictions import packages, values


class AlwaysSelfIntersect(values.base):
    def intersect(self, other):
        return self

    __hash__ = object.__hash__


class DummyIntersectingValues(values.base):

    """Helper to test PackageRestriction.intersect."""

    def __init__(self, val, iself=False, negate=False):
        object.__setattr__(self, "negate", negate)
        object.__setattr__(self, "val", val)

    def intersect(self, other):
        return DummyIntersectingValues((self.val, other.val))

    __hash__ = object.__hash__


class native_PackageRestrictionTest(TestCase):

    if packages.native_PackageRestriction is packages.PackageRestriction_base:
        kls = packages.PackageRestriction
    else:
        class kls(packages.PackageRestriction_mixin,
            packages.native_PackageRestriction):
            __slots__ = ()
            __inst_caching__ = True
    kls = staticmethod(kls)

    def test_eq(self):
        self.assertEquals(
            self.kls('one', values.AlwaysTrue),
            self.kls('one', values.AlwaysTrue))
        self.assertNotEquals(
            self.kls('one', values.AlwaysTrue),
            self.kls('one', values.AlwaysTrue, negate=True))
        self.assertNotEquals(
            self.kls('one', values.AlwaysTrue),
            self.kls('two', values.AlwaysTrue))
        self.assertNotEquals(
            self.kls('one', values.AlwaysTrue, negate=True),
            self.kls('one', values.AlwaysFalse, negate=True))

    def test_intersect(self):
        always_self = AlwaysSelfIntersect()
        p1 = self.kls('one', always_self)
        p1n = self.kls('one', always_self, negate=True)
        p2 = self.kls('two', always_self)
        self.assertIdentical(p1, p1.intersect(p1))
        self.assertIdentical(None, p1.intersect(p2))
        self.assertIdentical(None, p1n.intersect(p1))

        for negate in (False, True):
            d1 = self.kls(
                'one', DummyIntersectingValues(1), negate=negate)
            d2 = self.kls(
                'one', DummyIntersectingValues(2), negate=negate)
            i1 = d1.intersect(d2)
            self.failUnless(i1)
            self.assertEquals((1, 2), i1.restriction.val)
            self.assertEquals(negate, i1.negate)
            self.assertEquals('one', i1.attr)


class cpy_PackageRestrictionTest(native_PackageRestrictionTest):
    if packages.native_PackageRestriction is packages.PackageRestriction_base:
        skip = "cpython extension isn't available"
    else:
        kls = staticmethod(packages.PackageRestriction)


class ConditionalTest(TestCase):

    def test_eq(self):
        p = (packages.PackageRestriction('one', values.AlwaysTrue),)
        p2 = (packages.PackageRestriction('one', values.AlwaysFalse),)
        v = values.AlwaysTrue
        v2 = values.AlwaysFalse
        self.assertEquals(
            packages.Conditional('use', v, p),
            packages.Conditional('use', v, p))
        self.assertNotEqual(
            packages.Conditional('use', v2, p),
            packages.Conditional('use', v, p))
        self.assertNotEqual(
            packages.Conditional('use', v, p),
            packages.Conditional('use', v, p2))
        self.assertNotEqual(
            packages.Conditional('use1', v, p),
            packages.Conditional('use', v, p))
