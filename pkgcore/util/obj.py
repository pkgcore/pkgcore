# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from operator import attrgetter
from pkgcore.util.currying import pre_curry
from pkgcore.util.mappings import DictMixin

def alias_method(getter, self, *a, **kwd):
    return getter(self.__obj__)(*a, **kwd)

def instantiate(inst):
    delayed = object.__getattribute__(inst, "__delayed__")
    obj = delayed[1](*delayed[2], **delayed[3])
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

    def __new__(cls, desired_kls, func, *a, **kwd):
        o = object.__new__(cls)
        object.__setattr__(o, "__delayed__", (desired_kls, func, a, kwd))
        object.__setattr__(o, "__obj__", None)
        return o

    def __getattribute__(self, attr):
        obj = object.__getattribute__(self, "__obj__")
        if obj is None:
            if attr == "__class__":
                return object.__getattribute__(self, "__delayed__")[0]

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
        '__iter__', '__contains__',
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
    """Generate an objects that does not get initialized before it is used.

    The returned object can be passed around without triggering
    initialization. The first time it is actually used (an attribute
    is accessed) it is initialized once.

    The returned "fake" object cannot completely reliably mimic a
    builtin type. It will usually work but some corner cases may fail
    in confusing ways. Make sure to test if DelayedInstantiation has
    no unwanted side effects.

    @param resultant_kls: type object to fake an instance of.
    @param func: callable, the return value is used as initialized object.
    """
    o = class_cache.get(resultant_kls, None)
    if o is None:
        o = make_kls(resultant_kls)
        class_cache[resultant_kls] = o
    return o(resultant_kls, func, *a, **kwd)


slotted_dict_cache = {}
def make_SlottedDict_kls(keys):
    new_keys = tuple(sorted(keys))
    o = slotted_dict_cache.get(new_keys, None)
    if o is None:
        class SlottedDict(DictMixin):
            __slots__ = new_keys
            __externally_mutable__ = True

            def __init__(self, iterables=()):
                if iterables:
                    self.update(iterables)

            __setitem__ = object.__setattr__

            def __getitem__(self, key):
                try:
                    return getattr(self, key)
                except AttributeError:
                    raise KeyError(key)

            def __delitem__(self, key):
                # Python does not raise anything if you delattr an
                # unset slot (works ok if __slots__ is not involved).
                try:
                    getattr(self, key)
                except AttributeError:
                    raise KeyError(key)
                delattr(self, key)

            def __iter__(self):
                for k in self.__slots__:
                    if hasattr(self, k):
                        yield k

            def iterkeys(self):
                return iter(self)

            def itervalues(self):
                for k in self:
                    yield self[k]

            def get(self, key, default=None):
                return getattr(self, key, default)

            def pop(self, key, *a):
                # faster then the exception form...
                l = len(a)
                if l > 1:
                    raise TypeError("pop accepts 1 or 2 args only")
                if hasattr(self, key):
                    o = getattr(self, key)
                    object.__delattr__(self, key)
                elif l:
                    o = a[0]
                else:
                    raise KeyError(key)
                return o

            def clear(self):
                for k in self:
                    del self[k]

            def update(self, iterable):
                for k, v in iterable:
                    setattr(self, k, v)

            def __len__(self):
                return len(self.keys())

            def __contains__(self, key):
                return hasattr(self, key)

        o = SlottedDict
        slotted_dict_cache[new_keys] = o
    return o
