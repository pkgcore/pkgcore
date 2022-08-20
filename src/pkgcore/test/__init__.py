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


class malleable_obj:
    def __init__(self, **kwds):
        self.__dict__.update(kwds)
