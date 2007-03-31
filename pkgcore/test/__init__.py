# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Our unittest extensions."""


__all__ = ['scripts', 'SkipTest', 'TestCase', 'Todo']

from pkgcore import log
from snakeoil import test as snake_test

SkipTest = snake_test.SkipTest
Todo = snake_test.Todo

class TestCase(snake_test.TestCase):

    def assertLen(self, obj, length, msg=None):
        self.failUnless(len(obj) == length,
            msg or '%r needs to be len %i, is %i' % (obj, length, len(obj)))

    def assertInstance(self, obj, kls, msg=None):
        """
        assert that obj is an instance of kls
        """
        self.failUnless(isinstance(obj, kls),
            msg or '%r needs to be an instance of %r, is %r' % (obj, kls,
                getattr(obj, '__class__', "__class__ wasn't pullable")))

    def assertNotInstance(self, obj, kls, msg=None):
        """
        assert that obj is not an instance of kls
        """
        self.failIf(isinstance(obj, kls),
            msg or '%r must not be an instance of %r, is %r' % (obj, kls,
                getattr(obj, '__class__', "__class__ wasn't pullable")))

    def assertIdentical(self, this, other, reason=None):
        self.failUnless(
            this is other, reason or '%r is not %r' % (this, other))

    def assertNotIdentical(self, this, other, reason=None):
        self.failUnless(
            this is not other, reason or '%r is %r' % (this, other))

    def assertIn(self, needle, haystack, reason=None):
        self.failUnless(
            needle in haystack, reason or '%r not in %r' % (needle, haystack))

    def assertNotIn(self, needle, haystack, reason=None):
        self.failUnless(
            needle not in haystack, reason or '%r in %r' % (needle, haystack))

    def assertEqual(self, obj1, obj2, msg=None, reflective=True):
        self.failUnless(obj1 == obj2,
            msg or '%r != %r' % (obj1, obj2))
        if reflective:
            self.failUnless(not (obj1 != obj2),
                msg or 'not (%r != %r)' % (obj1, obj2))

    def assertNotEqual(self, obj1, obj2, msg=None, reflective=True):
        self.failUnless(obj1 != obj2, 
            msg or '%r == %r' % (obj1, obj2))
        if reflective:
            self.failUnless(not (obj1 == obj2),
                msg or 'not (%r == %r)' % (obj1, obj2))

    def assertEquals(self, obj1, obj2, msg=None):
        raise AssertionError("don't use assertEquals, use assertEqual")

    def assertNotEquals(self, obj1, obj2, msg=None):
        raise AssertionError("don't use assertNotEquals, use assertNotEqual")


class QuietLogger(log.logging.Handler):
    def emit(self, record):
        pass

quiet_logger = QuietLogger()


def protect_logging(target):
    def f(func):
        def f_inner(*args, **kwds):
            handlers = target.handlers[:]
            try:
                return func(*args, **kwds)
            finally:
                target.handlers[:] = handlers
        return f_inner
    return f


class TestRestriction(TestCase):

    def assertMatch(self, obj, args, mode='match', negated=False, msg=None):
        if msg is None:
            msg = ''
        else:
            msg = "; msg=" + msg
        if negated:
            self.assertFalse(getattr(obj, mode)(*args),
                msg="%r must not match %r, mode=%s, negated=%r%s" %
                    (obj, args, mode, negated, msg))
        else:
            self.assertTrue(getattr(obj, mode)(*args),
                msg="%r must match %r, mode=%s, not negated%s" %
                    (obj, args, mode, msg))

    def assertNotMatch(self, obj, target, mode='match', negated=False,
        msg=None):
        return self.assertMatch(obj, target, mode=mode, negated=not negated,
            msg=msg)

    def assertForceTrue(self, obj, target, negated=False, msg=None):
        return self.assertMatch(obj, target, mode='force_True',
            negated=negated, msg=msg)

    def assertNotForceTrue(self, obj, target, negated=False, msg=None):
        return self.assertNotMatch(obj, target, mode='force_True',
            negated=negated, msg=msg)

    def assertForceFalse(self, obj, target, negated=False, msg=None):
        return self.assertMatch(obj, target, mode='force_False',
            negated=negated, msg=msg)

    def assertNotForceFalse(self, obj, target, negated=False, msg=None):
        return self.assertNotMatch(obj, target, mode='force_False',
            negated=negated, msg=msg)

    def assertMatches(self, obj, args, force_args=None, negated=False,
        msg=None):
        if force_args is None:
            force_args = args
        self.assertMatch(obj, args, negated=negated, msg=msg)
        self.assertForceTrue(obj, force_args, negated=negated, msg=msg)
        self.assertNotForceFalse(obj, force_args, negated=negated, msg=msg)

    def assertNotMatches(self, obj, args, force_args=None, negated=False,
        msg=None):
        if force_args is None:
            force_args = args
        self.assertNotMatch(obj, args, negated=negated, msg=msg)
        self.assertNotForceTrue(obj, force_args, negated=negated, msg=msg)
        self.assertForceFalse(obj, force_args, negated=negated, msg=msg)


class mallable_obj(object):
    def __init__(self, **kwds):
        self.__dict__.update(kwds)
