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

    class generic__eq__(object):
        __slots__ = ("attrlist", "__weakref__")
    
        def __init__(self, *attrlist):
            self.attrlist = tuple(attrgetter(x) for x in attrlist)
    
        def __call__(self, inst1, inst2):
            if inst1 is inst2:
                return True
            for f in self.attrlist:
                if f(inst1) != f(inst2):
                    return False
            return True

    class generic__ne__(object):
        __slots__ = ("attrlist", "__weakref__")
    
        def __init__(self, *attrlist):
            self.attrlist = tuple(attrgetter(x) for x in attrlist)
    
        def __call__(self, inst1, inst2):
            if inst1 is inst2:
                return False
            for f in self.attrlist:
                if f(inst1) == f(inst2):
                    return False
            return True

    return generic__eq__(*attrlist), generic__ne__(attrlist)
