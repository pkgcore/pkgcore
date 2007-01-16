# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from pkgcore.test import TestCase

from pkgcore.restrictions import restriction


class SillyBool(restriction.base):
    """Extra stupid version of AlwaysBool to test base.force_{True,False}."""

    def __init__(self, negate=False):
        object.__setattr__(self, 'negate', negate)

    def match(self, *args, **kwargs):
        return not self.negate


class BaseTest(TestCase):

    def test_base(self):
        base = restriction.base()
        self.assertEquals(len(base), 1)
        # Just check repr and str do not raise
        self.assertTrue(str(base))
        self.assertTrue(repr(base))
        self.failUnless(hash(base))
        self.assertRaises(NotImplementedError, base.match)
        self.assertIdentical(None, base.intersect(base))

    def test_force(self):
        true = SillyBool(negate=False)
        false = SillyBool(negate=True)
        self.failUnless(true.force_True(None))
        self.failIf(true.force_False(None))
        self.failIf(false.force_True(None))
        self.failUnless(false.force_False(None))


class AlwaysBoolTest(TestCase):

    def test_true(self):
        true = restriction.AlwaysBool('foo', True)
        false = restriction.AlwaysBool('foo', False)
        self.failUnless(true.match(false))
        self.failIf(false.match(true))
        self.assertEquals(str(true), "always 'True'")
        self.assertEquals(str(false), "always 'False'")
        self.assertNotEqual(hash(true), hash(false))


class NoneMatch(restriction.base):

    """Only matches None."""

    def match(self, val):
        return val is None

    def __repr__(self):
        return '<NoneMatch>'

    def __str__(self):
        return 'NoneMatch'


class AnyMatchTest(TestCase):

    def test_basic(self):
        for negate in (False, True):
            inst = restriction.AnyMatch(NoneMatch(), 'spork', negate=negate)
            self.assertEqual(not negate, inst.match(['spork', None]))
            self.assertEqual(negate, inst.match(['spork']))
            self.assertEqual(negate, inst.match(()))
            # just test these do not traceback
            self.assertTrue(repr(inst))
            self.assertTrue(str(inst))
