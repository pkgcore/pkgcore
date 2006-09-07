# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from operator import attrgetter
from pkgcore.util.currying import pre_curry

def alias_method(getter, self, *a, **kwd):
    return getter(self.__obj__)(*a, **kwd)

class DelayInstantiation(object):
    """
    delay actual creation
    """
    
    def __new__(cls, desired_kls, *a, **kwd):
        o = object.__new__(cls)
        object.__setattr__(o, "__delayed__", (desired_kls, a, kwd))
        object.__setattr__(o, "__obj__", None)
        return o
    
    def __getattribute__(self, attr):
        obj = object.__getattribute__(self, "__obj__")
        if obj is None:
            delayed = object.__getattribute__(self, "__delayed__")
            obj = delayed[0](*delayed[1], **delayed[2])
            object.__setattr__(self, "__obj__", obj)
            object.__delattr__(self, "__delayed__")
        return obj
    
    # special case a few methods
    for x in ('__delattr__', '__doc__', '__hash__', '__reduce__', 
        '__reduce_ex__', '__repr__', '__setattr__', '__str__'):
        locals()[x] = pre_curry(alias_method, attrgetter(x))
    del x


