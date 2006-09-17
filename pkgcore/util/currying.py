# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
Function currying, generating a functor with a set of args/defaults pre bound.

L{pre_curry} and L{post_curry} return "normal" python functions.
L{partial} returns a callable object. The difference between
L{pre_curry} and L{partial} is this::

    >>> def func(arg=None, self=None):
    ...     return arg, self
    >>> curry = pre_curry(func, True)
    >>> part = partial(func, True)
    >>> class Test(object):
    ...     curry = pre_curry(func, True)
    ...     part = partial(func, True)
    ...     def __repr__(self):
    ...         return '<Test object>'
    >>> curry()
    (True, None)
    >>> Test().curry()
    (True, <Test object>)
    >>> part()
    (True, None)
    >>> Test().part()
    (True, None)

If your curried function is not used as a class attribute the results
should be identical. Because L{partial} has an implementation in c
while L{pre_curry} is python you should use L{partial} if possible.
"""

from operator import attrgetter

__all__ = [
    "pre_curry", "partial", "post_curry", "pretty_docs", "alias_class_method"]

def pre_curry(func, *args, **kwargs):
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


class native_partial(object):

    """Like pre_curry, but does not get turned into an instance method."""

    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def __call__(self, *moreargs, **morekwargs):
        kw = self.kwargs.copy()
        kw.update(morekwargs)
        return self.func(*(self.args + moreargs), **kw)

# Unused import, unable to import
# pylint: disable-msg=W0611,F0401
try:
    from functools import partial
except ImportError:
    try:
        from pkgcore.util._functools import partial
    except ImportError:
        partial = native_partial


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

    Useful for when setting has_key to __contains__ for example, and
    __contains__ may be overriden.
    """
    grab_attr = attrgetter(attr)

    def _asecond_level_call(self, *a, **kw):
        return grab_attr(self)(*a, **kw)

    return _asecond_level_call
