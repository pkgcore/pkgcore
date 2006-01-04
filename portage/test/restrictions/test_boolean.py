
from twisted.trial import unittest

from portage.restrictions import boolean, restriction
from portage.util import mappings


true = restriction.AlwaysBool('foo', True)
false = restriction.AlwaysBool('foo', False)


class AlwaysForcableBool(boolean.base):

    def force_True(self, action, *args):
        yield True

    match = force_False = force_True


class BaseTest(unittest.TestCase):

    def test_invalid_restrictions(self):
        self.assertRaises(TypeError, boolean.base, 'foo', 42)
        base = boolean.base('foo')
        self.assertRaises(TypeError, base.add_restriction, 42)
        self.assertRaises(TypeError, base.add_restriction)

    def test_init_finalize(self):
        final = boolean.base('foo', true, finalize=True)
        # TODO perhaps this should be more specific?
        self.assertRaises(Exception, final.add_restriction, false)

    def test_finalize(self):
        base = boolean.base('foo', true)
        base.add_restriction(false)
        base.finalize()
        # TODO perhaps this should be more specific?
        self.assertRaises(Exception, base.add_restriction, true)

    def test_base(self):
        base = boolean.base('foo', true, false)
        self.assertEquals(len(base), 2)
        self.assertEquals(list(base), [true, false])
        self.assertRaises(NotImplementedError, base.match, false)
        # TODO is the signature for these correct?
        self.assertRaises(NotImplementedError, base.force_False, false)
        self.assertRaises(NotImplementedError, base.force_True, false)
        self.assertIdentical(base[1], false)

    # TODO total_len? what does it do?

# TODO these tests are way too limited
class AndRestrictionTest(unittest.TestCase):

    def test_match(self):
        self.failUnless(boolean.AndRestriction('foo', true, true).match(None))
        self.failIf(
            boolean.AndRestriction('foo', false, true, true).match(None))
        self.failIf(
            boolean.AndRestriction('foo', true, false, true).match(None))

    def test_negate_match(self):
        self.failUnless(
            boolean.AndRestriction(
                'foo', false, true, negate=True).match(None))
        self.failUnless(
            boolean.AndRestriction(
                'foo', true, false, negate=True).match(None))
        self.failUnless(
            boolean.AndRestriction(
                'foo', false, false, negate=True).match(None))
        self.failIf(
            boolean.AndRestriction(
                'foo', true, true, negate=True).match(None))


class OrRestrictionTest(unittest.TestCase):

    def test_match(self):
        self.failUnless(boolean.OrRestriction('foo', true, true).match(None))
        self.failUnless(
            boolean.OrRestriction('foo', false, true, false).match(None))
        self.failUnless(
            boolean.OrRestriction('foo', true, false, false).match(None))
        self.failUnless(
            boolean.OrRestriction('foo', false, false, true).match(None))
        self.failIf(
            boolean.OrRestriction('foo', false, false).match(None))

    def test_negate_match(self):
        self.failIf(
            boolean.OrRestriction('foo', false, true, negate=True).match(None))
        self.failIf(
            boolean.OrRestriction('foo', true, false, negate=True).match(None))
        self.failIf(
            boolean.OrRestriction('foo', true, true, negate=True).match(None))
        self.failUnless(
            boolean.OrRestriction('foo', false, false, negate=True).match(None))
