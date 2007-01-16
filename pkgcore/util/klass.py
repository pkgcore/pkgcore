# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from operator import attrgetter
from pkgcore.util.caching import WeakInstMeta
from collections import deque

def native_GetAttrProxy(target):
    def reflected_getattr(self, attr):
        return getattr(getattr(self, target), attr)
    return reflected_getattr

def native_contains(self, key):
    try:
        self[key]
        return True
    except KeyError:
        return False

def native_get(self, key, default=None):
    try:
        return self[key]
    except KeyError:
        return default

attrlist_getter = attrgetter("__attr_comparison__")
def native_generic_eq(inst1, inst2):
    if inst1 is inst2:
        return True
    try:
        for attr in attrlist_getter(inst1):
            if getattr(inst1, attr) != getattr(inst2, attr):
                return False
        return True
    except AttributeError:
        return False

def native_generic_ne(inst1, inst2):
    if inst1 is inst2:
        return False
    try:
        for attr in attrlist_getter(inst1):
            if getattr(inst1, attr) == getattr(inst2, attr):
                return False
        return False
    except AttributeError:
        return True

try:
    from pkgcore.util._klass import (GetAttrProxy, contains, get,
        generic_eq, generic_ne)
except ImportError:
    GetAttrProxy = native_GetAttrProxy
    contains = native_contains
    get = native_get
    generic_eq = native_generic_eq
    generic_ne = native_generic_ne


def generic_equality(name, bases, scope, real_type=type):
    attrlist = scope.pop("__attr_comparison__", None)
    if attrlist is None:
        raise TypeError("__attr_comparison__ must be in the classes scope")
    for x in attrlist:
        if not isinstance(x, str):
            raise TypeError("all members of attrlist must be strings- "
                " got %r %s" % (type(x), repr(x)))

    scope["__attr_comparison__"] = tuple(attrlist)
    scope.setdefault("__eq__", generic_eq)
    scope.setdefault("__ne__", generic_ne)
    return real_type(name, bases, scope)


class chained_getter(object):
    def __metaclass__(name, bases, scope):
        return generic_equality(name, bases, scope, real_type=WeakInstMeta)
    __slots__ = ('namespace', 'chain')
    __fifo_cache__ = deque()
    __inst_caching__ = True
    __attr_comparison__ = ("namespace",)

    def __init__(self, namespace):
        self.namespace = namespace
        self.chain = map(attrgetter, namespace.split("."))
        if len(self.__fifo_cache__) > 10:
            self.__fifo_cache__.popleft()
        self.__fifo_cache__.append(self)

    def __hash__(self):
        return hash(self.namespace)

    def __call__(self, obj):
        o = obj
        for f in self.chain:
            o = f(o)
        return o
