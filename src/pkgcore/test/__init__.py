"""Our unittest extensions."""

from snakeoil.test import TestCase

from .. import log


class QuietLogger(log.logging.Handler):
    def emit(self, record):
        pass

quiet_logger = QuietLogger()


class callback_logger(log.logging.Handler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def emit(self, record):
        self.callback(record)


def protect_logging(target, forced_handlers=None):
    def f(func):
        def f_inner(*args, **kwds):
            handlers = target.handlers[:]
            try:
                if forced_handlers:
                    target.handlers[:] = list(forced_handlers)
                return func(*args, **kwds)
            finally:
                target.handlers[:] = handlers
        return f_inner
    return f


def silence_logging(target):
    return protect_logging(target, forced_handlers=[quiet_logger])


class TestRestriction(TestCase):

    def _assertMatch(self, obj, args, mode='match', negated=False, msg=None):
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

    def assertMatch(self, obj, target, mode='match', negated=False, msg=None):
        return self._assertMatch(obj, (target,), mode=mode, negated=negated, msg=msg)

    def assertNotMatch(self, obj, target, mode='match', negated=False,
        msg=None):
        return self.assertMatch(obj, target, mode=mode, negated=not negated,
            msg=msg)


    def assertMatches(self, obj, target, force_args=None, negated=False,
        msg=None):
        if force_args is None:
            force_args = (target,)
        self.assertMatch(obj, target, negated=negated, msg=msg)
        self.assertForceTrue(obj, force_args, negated=negated, msg=msg)
        self.assertNotForceFalse(obj, force_args, negated=negated, msg=msg)

    def assertNotMatches(self, obj, target, force_args=None, negated=False,
        msg=None):
        if force_args is None:
            force_args = (target,)
        self.assertNotMatch(obj, target, negated=negated, msg=msg)
        self.assertNotForceTrue(obj, force_args, negated=negated, msg=msg)
        self.assertForceFalse(obj, force_args, negated=negated, msg=msg)

    def assertForceTrue(self, obj, target, negated=False, msg=None):
        return self._assertMatch(obj, target, mode='force_True',
            negated=negated, msg=msg)

    def assertNotForceTrue(self, obj, target, negated=False, msg=None):
        return self._assertMatch(obj, target, mode='force_True',
            negated=not negated, msg=msg)

    def assertForceFalse(self, obj, target, negated=False, msg=None):
        return self._assertMatch(obj, target, mode='force_False',
            negated=negated, msg=msg)

    def assertNotForceFalse(self, obj, target, negated=False, msg=None):
        return self._assertMatch(obj, target, mode='force_False',
            negated=not negated, msg=msg)


class malleable_obj:
    def __init__(self, **kwds):
        self.__dict__.update(kwds)
