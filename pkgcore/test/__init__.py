# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Our unittest extensions."""

__all__ = ('TestCase', 'SkipTest', 'Todo')


from snakeoil.test import TestCase as orig_TestCase, SkipTest, Todo
from pkgcore import log

class TestCase(orig_TestCase):

    def assertRaisesMsg(self, msg, excClass, callableObj, *args, **kwargs):
        """Fail unless an exception of class excClass is thrown
           by callableObj when invoked with arguments args and keyword
           arguments kwargs. If a different type of exception is
           thrown, it will not be caught, and the test case will be
           deemed to have suffered an error, exactly as for an
           unexpected exception.
        """
        try:
            callableObj(*args, **kwargs)
        except excClass:
            return
        else:
            if hasattr(excClass,'__name__'): excName = excClass.__name__
            else: excName = str(excClass)
            raise self.failureException, "%s not raised: %s" % (excName, msg)


class QuietLogger(log.logging.Handler):
    def emit(self, record):
        pass

quiet_logger = QuietLogger()


class callback_logger(log.logging.Handler):
    def __init__(self, callback):
        log.logging.Handler.__init__(self)
        self.callback = callback

    def emit(self, record):
        self.callback(record)


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
