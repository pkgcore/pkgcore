# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

def native_GetAttrProxy(target):
    def reflected_getattr(self, attr):
        return getattr(getattr(self, target), attr)
    return reflected_getattr

try:
    from pkgcore.util._klass import GetAttrProxy
except ImportError:
    GetAttrProxy = native_GetAttrProxy
