# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from operator import attrgetter

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
    for attr in attrlist_getter(inst1):
        if getattr(inst1, attr) != getattr(inst2, attr):
           return False
    return True

def native_generic_ne(inst1, inst2):
    if inst1 is inst2:
        return False
    for attr in attrlist_getter(inst1):
        if getattr(inst1, attr) == getattr(inst2, attr):
            return False
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

def generic_equality(name, bases, scope):
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
    return type(name, bases, scope)
