# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

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
