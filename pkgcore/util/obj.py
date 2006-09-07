# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from operator import attrgetter
from pkgcore.util.currying import pre_curry

def alias_method(getter, self, *a, **kwd):
    return getter(self.__obj__)(*a, **kwd)

def instantiate(inst):
    delayed = object.__getattribute__(inst, "__delayed__")
    obj = delayed[0](*delayed[1], **delayed[2])
    object.__setattr__(inst, "__obj__", obj)
    object.__delattr__(inst, "__delayed__")
    return obj


# we exempt __getattribute__ since we cover it already, same
# for __new__ and __init__
base_kls_descriptors = frozenset(
    ('__delattr__', '__doc__', '__hash__', '__reduce__', 
        '__reduce_ex__', '__repr__', '__setattr__', '__str__'))

class BaseDelayedObject(object):
    """
    delay actual instantiation
    """
    
    def __new__(cls, desired_kls, *a, **kwd):
        o = object.__new__(cls)
        object.__setattr__(o, "__delayed__", (desired_kls, a, kwd))
        object.__setattr__(o, "__obj__", None)
        return o
    
    def __getattribute__(self, attr):
        obj = object.__getattribute__(self, "__obj__")
        if obj is None:
            obj = instantiate(self)
            # now we grow some attributes.

        if attr == "__obj__":
            # special casing for alias_method
            return obj
        return getattr(obj, attr)
    
    # special case the normal descriptors
    for x in base_kls_descriptors:
        locals()[x] = pre_curry(alias_method, attrgetter(x))
    del x


# note that we ignore __getattribute__; we already handle it.
kls_descriptors = frozenset([
        # simple comparison protocol...
        '__cmp__', 
        # rich comparison protocol...
        '__le__', '__lt__', '__eq__', '__ne__', '__gt__', '__ge__',
        # unicode conversion
        '__unicode__',
        # truth...
        '__nonzero__',
        # container protocol...
        '__len__', '__getitem__', '__setitem__', '__delitem__',
        '__iter__', '__contains__'
        # deprecated sequence protocol bits...
        '__getslice__', '__setslice__', '__delslice__',
        # numeric...
        '__add__', '__sub__', '__mul__', '__floordiv__', '__mod__',
        '__divmod__', '__pow__', '__lshift__', '__rshift__',
        '__and__', '__xor__', '__or__', '__div__', '__truediv__',
        '__rad__', '__rsub__', '__rmul__', '__rdiv__', '__rtruediv__',
        '__rfloordiv__', '__rmod__', '__rdivmod__', '__rpow__',
        '__rlshift__', '__rrshift__', '__rand__', '__rxor__', '__ror__',
        '__iadd__', '__isub__', '__imul__', '__idiv__', '__itruediv__',
        '__ifloordiv__', '__imod__', '__ipow__', '__ilshift__',
        '__irshift__', '__iand__', '__ixor__', '__ior__',
        '__neg__', '__pos__', '__abs__', '__invert__', '__complex__',
        '__int__', '__long__', '__float__', '__oct__', '__hex__',
        '__coerce__',
        # remaining...
        '__call__'])

descriptor_overrides = dict((k, pre_curry(alias_method, attrgetter(k)))
    for k in kls_descriptors)

method_cache = {}
def make_kls(kls):
    special_descriptors = tuple(sorted(kls_descriptors.intersection(dir(kls))))
    if not special_descriptors:
        return BaseDelayedObject
    o = method_cache.get(special_descriptors, None)
    if o is None:
        class CustomDelayedObject(BaseDelayedObject):
            locals().update((k, descriptor_overrides[k])
                for k in special_descriptors)

        o = CustomDelayedObject
        method_cache[special_descriptors] = o
    return o

def DelayedInstantiation_kls(kls, *a, **kwd):
    return DelayedInstantiation(kls, kls, *a, **kwd)

class_cache = {}
def DelayedInstantiation(resultant_kls, func, *a, **kwd):
    o = class_cache.get(resultant_kls, None)
    if o is None:
        o = make_kls(resultant_kls)
        class_cache[resultant_kls] = o
    return o(func, *a, **kwd)
    
    
