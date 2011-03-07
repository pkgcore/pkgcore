# Copyright: 2006-2009 Brian Harring <ferringb@gmail.com
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

from pkgcore.test import TestCase
from snakeoil.test import mk_cpy_loadable_testcase
from pkgcore import log
from pkgcore.restrictions import packages, values
from pkgcore.test import (protect_logging, TestRestriction, malleable_obj,
    quiet_logger, callback_logger)


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


class native_PackageRestrictionTest(TestRestriction):

    if packages.native_PackageRestriction is packages.PackageRestriction_base:
        kls = packages.PackageRestriction
    else:
        class kls(packages.native_PackageRestriction,
            packages.PackageRestriction_mixin):
            __slots__ = ()
            __inst_caching__ = packages.PackageRestriction.__inst_caching__

    kls = staticmethod(kls)

    @protect_logging(log.logging.root)
    def test_matching(self):
        strexact = values.StrExactMatch

        log.logging.root.handlers = [quiet_logger]
        args = [malleable_obj(category="foon", package="dar")]
        self.assertMatches(self.kls("category", strexact("foon")), args)
        self.assertMatches(self.kls("package", strexact("dar")), args)
        self.assertNotMatches(self.kls("package", strexact("dar"), negate=True),
            args)
        self.assertNotMatches(self.kls("package", strexact("foon")), args)

        self.assertMatches(self.kls("package", strexact("foon"), negate=True),
            args)
        excepts = []
        # no msg should be thrown, it wasn't an unexpected exception

        log.logging.root.addHandler(callback_logger(excepts.append))
        self.assertNotMatches(self.kls("foon", AlwaysSelfIntersect), args)
        self.assertFalse(excepts)

        self.assertMatches(self.kls("foon", AlwaysSelfIntersect, negate=True),
            args)
        self.assertFalse(excepts)

        class foo:
            def __getattr__(self, attr):
                if attr.startswith("exc"):
                    raise exceptions_d.get(attr[4:], None)()
                raise AttributeError("monkey lover")

        exceptions_d = {"KeyboardInterrupt":KeyboardInterrupt,
            "RuntimeError":RuntimeError, "SystemExit":SystemExit}

        for mode in ("match", "force_True", "force_False"):
            excepts[:] = []
            self.assertRaises(AttributeError,
                getattr(self.kls("foon", AlwaysSelfIntersect), mode),
                foo())
            self.assertEqual(len(excepts), 1,
                msg="expected one exception, got %r" % excepts)

            # ensure various exceptions are passed through
            for k in (KeyboardInterrupt, RuntimeError, SystemExit):
                self.assertRaises(k,
                    getattr(self.kls("exc_%s" % k.__name__,
                        AlwaysSelfIntersect), mode),
                    foo())

        # check that it only does string comparison in exception catching.
        class foo:
            def __cmp__(self, other):
                raise TypeError

            def __getattr__(self, attr):
                raise AttributeError(self, attr)

        self.assertFalse(self.kls("foon", AlwaysSelfIntersect).match(foo()))

    def test_attr(self):
        self.assertEqual(self.kls('val', values.AlwaysTrue).attr,
            'val')
        self.assertEqual(self.kls('val.dar', values.AlwaysTrue).attr,
            ('val', 'dar'))

    def test_eq(self):
        self.assertEqual(
            self.kls('one', values.AlwaysTrue),
            self.kls('one', values.AlwaysTrue))
        self.assertNotEqual(
            self.kls('one', values.AlwaysTrue),
            self.kls('one', values.AlwaysTrue, negate=True))
        self.assertNotEqual(
            self.kls('one', values.AlwaysTrue),
            self.kls('two', values.AlwaysTrue))
        self.assertNotEqual(
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
            self.assertTrue(i1)
            self.assertEqual((1, 2), i1.restriction.val)
            self.assertEqual(negate, i1.negate)
            self.assertEqual('one', i1.attr)

    def test_hash(self):
        inst = self.kls('one.dar', AlwaysSelfIntersect())
        hash(inst)


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
        self.assertEqual(
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

test_cpy_used = mk_cpy_loadable_testcase('pkgcore.restrictions._restrictions',
    "pkgcore.restrictions.packages", "PackageRestriction_base", "PackageRestriction")
