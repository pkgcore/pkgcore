# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from pkgcore.test import TestCase, protect_logging, TestRestriction
from pkgcore.restrictions import packages, values
from pkgcore.util.currying import partial, post_curry
from pkgcore import log
import exceptions

class callback_logger(log.logging.Handler):
    def __init__(self, callback):
        log.logging.Handler.__init__(self)
        self.callback = callback
    
    def emit(self, record):
        self.callback(record)


class quiet_logger(log.logging.Handler):
    def emit(self, record):
        pass

quiet_logger = quiet_logger()

class AlwaysSelfIntersect(values.base):
    def intersect(self, other):
        return self

    __hash__ = object.__hash__

class simple_obj(object):
    def __init__(self, **kwds):
        self.__dict__.update(kwds)


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
        class kls(packages.PackageRestriction_mixin,
            packages.native_PackageRestriction):
            __slots__ = ()
            __inst_caching__ = packages.PackageRestriction.__inst_caching__

    kls = staticmethod(kls)

    @protect_logging(log.logging.root)
    def run_check(self, mode='match'):
        strexact = values.StrExactMatch

        negated = mode == 'force_False'
        assertMatch = partial(self.assertMatch, mode=mode,
            negated=negated)
        assertNotMatch = partial(self.assertNotMatch, mode=mode,
            negated=negated)


        log.logging.root.handlers = [quiet_logger]
        obj = simple_obj(category="foon", package="dar")
        assertMatch(self.kls("category", strexact("foon")), obj)
        assertMatch(self.kls("package", strexact("dar")), obj)
        assertNotMatch(self.kls("package", strexact("dar"), negate=True), obj)
        assertNotMatch(self.kls("package", strexact("foon")), obj)
        assertMatch(self.kls("package", strexact("foon"), negate=True), obj)
        excepts = []
        # no msg should be thrown, it wasn't an unexpected exception

        log.logging.root.addHandler(callback_logger(excepts.append))
        assertNotMatch(self.kls("foon", AlwaysSelfIntersect), obj,
            mode=mode)
        self.assertFalse(excepts)

        assertMatch(self.kls("foon", AlwaysSelfIntersect, negate=True), obj,
            mode=mode)
        self.assertFalse(excepts)

        class foo:
            def __getattr__(self, attr):
                if attr.startswith("exc"):
                    import exceptions
                    raise getattr(exceptions, attr[4:])()
                raise AttributeError("monkey lover")

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

    test_match = run_check
    
    test_force_true = post_curry(run_check, mode='force_True')
    test_force_false = post_curry(run_check, mode='force_False')

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
