# Copyright: 2007 Brian Harring <ferringb@gmail.com>: BSD/GPL2
# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from pkgcore.test import TestRestriction
from pkgcore.restrictions import restriction
from snakeoil.currying import partial


class SillyBool(restriction.base):
    """Extra stupid version of AlwaysBool to test base.force_{True,False}."""

    __slots__ = ('negate',)

    def __init__(self, negate=False):
        object.__setattr__(self, 'negate', negate)

    def match(self, *args, **kwargs):
        return not self.negate


class BaseTest(TestRestriction):

    bool_kls = SillyBool

    def test_base(self):
        base = restriction.base()
        self.assertEqual(len(base), 1)
        # Just check repr and str do not raise
        self.assertTrue(str(base))
        self.assertTrue(repr(base))
        self.failUnless(hash(base))
        self.assertRaises(NotImplementedError, base.match)
        self.assertIdentical(None, base.intersect(base))

    def test_it(self):
        true = self.bool_kls(negate=False)
        false = self.bool_kls(negate=True)
        args = [None]

        self.assertMatch(true, args)
        self.assertForceTrue(true, args)
        self.assertNotForceFalse(true, args)

        self.assertNotMatch(false, args)
        self.assertNotForceTrue(false, args)
        self.assertForceFalse(false, args)


class AlwaysBoolTest(TestRestriction):

    bool_kls = partial(restriction.AlwaysBool, 'foo')

    def test_true(self):
        true = self.bool_kls(True)
        false = self.bool_kls(False)
        self.assertMatch(true, false)
        self.assertForceTrue(true, false)
        self.assertNotForceFalse(true, false)

        self.assertNotMatch(false, true)
        self.assertNotForceTrue(false, true)
        self.assertForceFalse(false, true)

        self.assertEqual(str(true), "always 'True'")
        self.assertEqual(str(false), "always 'False'")
        self.assertNotEqual(hash(true), hash(false))
        self.assertEqual(hash(true),
            hash(self.bool_kls(True)))
        self.assertEqual(hash(false),
            hash(self.bool_kls(False)))
        self.assertEqual(true, self.bool_kls(True))
        self.assertEqual(false, self.bool_kls(False))
        self.assertNotEqual(true, false)


class NoneMatch(restriction.base):

    """Only matches None."""

    __slots__ = ()

    def match(self, val):
        return val is None

    def __repr__(self):
        return '<NoneMatch>'

    def __str__(self):
        return 'NoneMatch'


class AnyMatchTest(TestRestriction):

    def test_basic(self):
        for negate in (False, True):
            inst = restriction.AnyMatch(NoneMatch(), 'spork', negate=negate)
            self.assertMatch(inst, [['spork', None]], negated=negate)
            self.assertNotMatch(inst, [['spork']], negated=negate)
            self.assertNotMatch(inst, [()], negated=negate)

            # just test these do not traceback
            self.assertTrue(repr(inst))
            self.assertTrue(str(inst))
