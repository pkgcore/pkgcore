# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Our unittest extensions."""


__all__ = ['scripts', 'SkipTest', 'TestCase']


import sys
import warnings
import unittest


def _tryResultCall(result, methodname, *args):
    method = getattr(result, methodname, None)
    if method is not None:
        method(*args)


class SkipTest(Exception):
    """Raise to skip a test."""


class Todo(object):

    def __init__(self, reason, errors=None):
        self.reason = reason
        self.errors = errors

    @classmethod
    def parse(cls, todo):
        if isinstance(todo, basestring):
            return cls(reason=todo)
        errors, reason = todo
        try:
            errors = list(errors)
        except TypeError:
            errors = [errors]
        return cls(reason=reason, errors=errors)

    def expected(self, exception):
        if self.errors is None:
            return True
        for error in self.errors:
            # We want an exact match here.
            if exception is error:
                return True
        return False


class TestCase(unittest.TestCase, object):

    """Our additions to the standard TestCase.

    This is meant to interact with twisted trial's runner/result objects
    gracefully.

    Extra features:
     - Some extra assert* methods.
     - Support "skip" attributes (strings) on both TestCases and methods.
       Such tests do not run at all under "normal" unittest and get a nice
       "skip" message under trial.
     - Support "todo" attributes (strings, tuples of (ExceptionClass, string)
       or tuples of ((ExceptionClass1, ExceptionClass2, ...), string) on both
       TestCases and methods. Such tests are expected to fail instead of pass.
       If they do succeed that is treated as an error under "normal" unittest.
       If they fail they are ignored under "normal" unittest.
       Under trial both expected failure and unexpected success are reported
       specially.
     - Support "suppress" attributes on methods. They should be a sequence of
       (args, kwargs) tuples suitable for passing to
       L{warnings.filterwarnings}. The method runs with those additions.
    """

    def __init__(self, methodName='runTest'):
        # This method exists because unittest.py in python 2.4 stores
        # the methodName as __testMethodName while 2.5 uses
        # _testMethodName.
        self._testMethodName = methodName
        unittest.TestCase.__init__(self, methodName)

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

    # unittest and twisted each have a differing count of how many frames
    # to pop off when displaying an exception; thus we force an extra
    # frame so that trial results are usable
    @staticmethod
    def forced_extra_frame(test):
        test()

    def run(self, result=None):
        if result is None:
            result = self.defaultTestResult()
        testMethod = getattr(self, self._testMethodName)
        result.startTest(self)
        try:
            skip = getattr(testMethod, 'skip', getattr(self, 'skip', None))
            todo = getattr(testMethod, 'todo', getattr(self, 'todo', None))
            if todo is not None:
                todo = Todo.parse(todo)
            if skip is not None:
                _tryResultCall(result, 'addSkip', self, skip)
                return

            try:
                self.setUp()
            except KeyboardInterrupt:
                raise
            except:
                result.addError(self, sys.exc_info())
                return

            suppressions = getattr(testMethod, 'suppress', ())
            for args, kwargs in suppressions:
                warnings.filterwarnings(*args, **kwargs)
            addedFilters = warnings.filters[:len(suppressions)]
            ok = False
            try:
                try:
                    self.forced_extra_frame(testMethod)
                    ok = True
                except self.failureException:
                    exc = sys.exc_info()
                    if todo is not None and todo.expected(exc[0]):
                        _tryResultCall(result, 'addExpectedFailure',
                                       self, str(exc[1]), todo)
                    else:
                        result.addFailure(self, exc)
                except SkipTest, e:
                    _tryResultCall(result, 'addSkip', self, str(e))
                except KeyboardInterrupt:
                    raise
                except:
                    exc = sys.exc_info()
                    if todo is not None and todo.expected(exc[0]):
                        _tryResultCall(result, 'addExpectedFailure',
                                       self, str(exc[1]), todo)
                    else:
                        result.addError(self, exc)
                    # There is a tb in this so do not keep it around.
                    del exc
            finally:
                for filterspec in addedFilters:
                    if filterspec in warnings.filters:
                        warnings.filters.remove(filterspec)

            try:
                self.tearDown()
            except KeyboardInterrupt:
                raise
            except:
                result.addError(self, sys.exc_info())
                ok = False

            if ok:
                if todo is not None:
                    _tryResultCall(result, 'addUnexpectedSuccess', self, todo)
                else:
                    result.addSuccess(self)

        finally:
            result.stopTest(self)


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
        
