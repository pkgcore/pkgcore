# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
function currying, generating a functor with a set of args/defaults pre bound
"""

from operator import attrgetter

__all__ = ["pre_curry", "post_curry", "pretty_docs", "alias_class_method"]

def native_pre_curry(func, *args, **kwargs):
    """passed in args are prefixed, with further args appended"""

    if not kwargs:
        def callit(*moreargs, **morekwargs):
            return func(*(args + moreargs), **morekwargs)
    elif not args:
        def callit(*moreargs, **morekwargs):
            kw = kwargs.copy()
            kw.update(morekwargs)
            return func(*moreargs, **kw)
    else:
        def callit(*moreargs, **morekwargs):
            kw = kwargs.copy()
            kw.update(morekwargs)
            return func(*(args+moreargs), **kw)

    callit.func = func
    return callit

# native_pre_curry is always defined, if pre_curry is not identical to
# native_pre_curry the tests test both.
try:
    from functools import partial as pre_curry
except ImportError:
    pre_curry = native_pre_curry


def post_curry(func, *args, **kwargs):
    """passed in args are appended to any further args supplied"""

    if not kwargs:
        def callit(*moreargs, **morekwargs):
            return func(*(moreargs+args), **morekwargs)
    elif not args:
        def callit(*moreargs, **morekwargs):
            kw = morekwargs.copy()
            kw.update(kwargs)
            return func(*moreargs, **kw)
    else:
        def callit(*moreargs, **morekwargs):
            kw = morekwargs.copy()
            kw.update(kwargs)
            return func(*(moreargs+args), **kw)

    callit.func = func
    return callit

def pretty_docs(wrapped, extradocs=None):
    wrapped.__module__ = wrapped.func.__module__
    doc = wrapped.func.__doc__
    if extradocs is None:
        wrapped.__doc__ = doc
    else:
        wrapped.__doc__ = extradocs
    return wrapped


def alias_class_method(attr):
    """at runtime, redirect to another method

    attr is the desired attr name to lookup, and supply all later passed in
    args/kws to

    Useful for when setting has_key to __contains__ for example, and __contains__ may be
    overriden
    """
    grab_attr = attrgetter(attr)

    def _asecond_level_call(self, *a, **kw):
        return grab_attr(self)(*a, **kw)

    return _asecond_level_call
