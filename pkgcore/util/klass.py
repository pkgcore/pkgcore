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

try:
    from pkgcore.util._klass import GetAttrProxy, contains, get
except ImportError:
    GetAttrProxy = native_GetAttrProxy
    contains = native_contains
    get = native_get


def generic_equality(*attrlist):

    attrlist = tuple(attrgetter(x) for x in attrlist)

    def generic__eq__(inst1, inst2, attrlist=attrlist):
        if inst1 is inst2:
            return True
        for f in attrlist:
            if f(inst1) != f(inst2):
               return False
        return True

    def generic__ne__(inst1, inst2, attrlist=attrlist):
        if inst1 is inst2:
            return False
        for f in attrlist:
            if f(inst1) == f(inst2):
                return False
        return True

    return generic__eq__, generic__ne__
