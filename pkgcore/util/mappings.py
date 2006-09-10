# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
miscellanious mapping/dict related classes
"""

import operator
from itertools import imap, chain, ifilterfalse, izip
from pkgcore.util.currying import alias_class_method
from collections import deque


class DictMixin(object):
    """
    new style class replacement for L{UserDict.DictMixin}
    designed around iter* methods rather then forcing lists as DictMixin does
    """

    __slots__ = ()

    __externally_mutable__ = True
    
    def __init__(self, iterable=[]):
        for k,v in iterable:
            self[k] = v
    
    def __iter__(self):
        return self.iterkeys()
    
    def keys(self):
        return list(self.iterkeys())
    
    def values(self):
        return list(self.itervalues())
    
    def items(self):
        return list(self.iteritems())
    
    def update(self, iterable):
        for k,v in iterable:
            self[k] =v
    
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
   
    # default cmp actually operates based on key len comparison, oddly enough
    def __cmp__(self, other):
        for k1, k2 in izip(self, other):
            c = cmp(k1, k2)
            if c != 0:
                return c
            c = cmp(self[k1], other[k2])
            if c != 0:
                return c
        c = cmp(len(self), len(other))
        return c
    
    def __eq__(self, other):
        return self.__cmp__(other) == 0
    
    def __ne__(self, other):
        return self.__cmp__(other) != 0
    
    def pop(self, key, *args):
        if not self.__externally_mutable__:
            raise AttributeError(self, "pop")
        if len(args) > 1:
            raise TypeError("pop expects at most 2 arguements, got %i" %
                len(args) + 1)
        try:
            val = self[key]
        except KeyError:
            if args:
                return args[0]
            raise
        del self[key]
        return val
    
    def setdefault(self, key, default=None):
        if not self.__externally_mutable__:
            raise AttributeError(self, "setdefault")
        if key in self:
            return self[key]
        self[key] = default
        return default

    def has_key(self, key):
        return key in self
        
    def iterkeys(self):
        raise NotImplementedError(self, "iterkeys")

    def itervalues(self):
        return imap(self.__getitem__, self)

    def iteritems(self):
        for k in self:
            yield k, self[k]
        
    def __getitem__(self, key):
        raise NotImplementedError(self, "__getitem__")
    
    def __setitem__(self, key, val):
        if not self.__externally_modifiable__:
            raise AttributeError(self, "__setitem__")
        raise NotImplementedError(self, "__setitem__")
    
    def __delitem__(self, key):
        if not self.__externally_modifiable__:
            raise AttributeError(self, "__delitem__")
        raise NotImplementedError(self, "__delitem__")
        
    def __contains__(self, key):
        raise NotImplementedError(self, "__contains__")

    def clear(self):
        if not self.__externally_mutable__:
            raise AttributeError(self, "clear")
        # crappy, override if faster method exists.
        map(self.__delitem__, self.keys())
    
    def __len__(self):
        c = 0
        for x in self:
            c += 1
        return c
    
    def popitem(self):
        if not self.__externally_mutable__:
            raise AttributeError(self, "popitem")
        # do it this way so python handles the stopiteration; faster
        for key, val in self.iteritems():
            del self[key]
            return key,val
        raise KeyError("container is empty")


class LazyValDict(DictMixin):

    """
    Mapping that loads values via a callable

    given a function to get keys, and to look up the val for those keys, it'll
    lazy load key definitions, and values as requested
    """
    __slots__ = ("_keys", "_keys_func", "_vals", "_val_func")
    __externally_mutable__ = False

    def __init__(self, get_keys_func, get_val_func):
        """
        @param get_keys_func: either a container, or func to call to get keys.
        @param get_val_func: a callable that is JIT called
            with the key requested.
        """
        if not callable(get_val_func):
            raise TypeError("get_val_func isn't a callable")
        if hasattr(get_keys_func, "__iter__"):
            self._keys = get_keys_func
            self._keys_func = None
        else:
            if not callable(get_keys_func):
                raise TypeError(
                    "get_keys_func isn't iterable nor is it callable")
            self._keys_func = get_keys_func
        self._val_func = get_val_func
        self._vals = {}

    def __getitem__(self, key):
        if self._keys_func is not None:
            self._keys = set(self._keys_func())
            self._keys_func = None
        if key in self._vals:
            return self._vals[key]
        if key in self._keys:
            v = self._vals[key] = self._val_func(key)
            return v
        raise KeyError(key)

    def keys(self):
        if self._keys_func is not None:
            self._keys = set(self._keys_func())
            self._keys_func = None
        return list(self._keys)

    def iterkeys(self):
        if self._keys_func is not None:
            self._keys = set(self._keys_func())
            self._keys_func = None
        return iter(self._keys)

    def itervalues(self):
        return imap(self.__getitem__, self.iterkeys())

    def iteritems(self):
        return ((k, self[k]) for k in self.iterkeys())

    def __contains__(self, key):
        if self._keys_func is not None:
            self._keys = set(self._keys_func())
            self._keys_func = None
        return key in self._keys

    def __len__(self):
        return len(self._keys)


class ProtectedDict(DictMixin):

    """
    Mapping wrapper storing changes to a dict without modifying the original.

    Changes are stored in a secondary dict, protecting the underlying
    mapping from changes.
    """

    __slots__ = ("orig", "new", "blacklist")

    def __init__(self, orig):
        self.orig = orig
        self.new = {}
        self.blacklist = {}

    def __setitem__(self, key, val):
        self.new[key] = val
        if key in self.blacklist:
            del self.blacklist[key]

    def __getitem__(self, key):
        if key in self.new:
            return self.new[key]
        if key in self.blacklist:
            raise KeyError(key)
        return self.orig[key]

    def __delitem__(self, key):
        if key in self.new:
            del self.new[key]
            return
        elif key in self.orig:
            if key not in self.blacklist:
                self.blacklist[key] = True
                return
        raise KeyError(key)

    def iterkeys(self):
        for k in self.new.iterkeys():
            yield k
        for k in self.orig.iterkeys():
            if k not in self.blacklist and k not in self.new:
                yield k

    def __contains__(self, key):
        return key in self.new or (key not in self.blacklist and
                                   key in self.orig)


class ImmutableDict(dict):

    """Immutable Dict, non changable after instantiating"""

    _hash_key_grabber = operator.itemgetter(0)

    def __delitem__(self, *args):
        raise TypeError("non modifiable")

    __setitem__ = __delitem__
    clear = __delitem__
    update = __delitem__
    pop = __delitem__
    popitem = __delitem__
    setdefault = __delitem__

    def __hash__(self):
        k = self.items()
        k.sort(key=self._hash_key_grabber)
        return hash(tuple(k))

    __delattr__ = __setitem__
    __setattr__ = __setitem__


class IndeterminantDict(dict):

    """A wrapped dict with constant defaults, and a function for other keys."""

    __slots__ = ("__initial", "__pull")

    def __init__(self, pull_func, starter_dict=None):
        dict.__init__(self)
        if starter_dict is None:
            self.__initial = {}
        else:
            self.__initial = starter_dict
        self.__pull = pull_func

    def __getitem__(self, key):
        if key in self.__initial:
            return self.__initial[key]
        else:
            return self.__pull(key)

    def get(self, key, val=None):
        try:
            return self[key]
        except KeyError:
            return val

    def __hash__(self):
        raise TypeError("non hashable")

    def __delitem__(self, *args):
        raise TypeError("non modifiable")

    def pop(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
    
    clear = update = popitem = setdefault = __setitem__ = __delitem__
    __iter__ = keys = values = items = __len__ = __delitem__
    iteritems = iterkeys = itervalues = __delitem__


class StackedDict(DictMixin):

    """A non modifiable dict that makes multiple dicts appear as one"""

    def __init__(self, *dicts):
        self._dicts = dicts

    def __getitem__(self, key):
        for x in self._dicts:
            if key in x:
                return x[key]
        raise KeyError(key)

    def iterkeys(self):
        s = set()
        for k in ifilterfalse(s.__contains__, chain(*map(iter, self._dicts))):
            s.add(k)
            yield k

    def __contains__(self, key):
        for x in self._dicts:
            if key in x:
                return True
        return False

    def __setitem__(self, *a):
        raise TypeError("non modifiable")

    __delitem__ = clear = __setitem__


class OrderedDict(DictMixin):

    """Dict that preserves insertion ordering which is used for iteration ops"""

    __slots__ = ("_data", "_order")

    def __init__(self, iterable=()):
        self._order = deque()
        self._data = {}
        for k, v in iterable:
            self[k] = v

    def __setitem__(self, key, val):
        if key not in self:
            self._order.append(key)
        self._data[key] = val

    def __delitem__(self, key):
        del self._data[key]

        for idx, o in enumerate(self._order):
            if o == key:
                del self._order[idx]
                break
        else:
            raise AssertionError("orderdict lost it's internal ordering")

    def __getitem__(self, key):
        return self._data[key]

    def __len__(self):
        return len(self._order)

    def iterkeys(self):
        return iter(self._order)

    def clear(self):
        dict.clear(self)
        self._order = deque()

    def __contains__(self, key):
        return key in self._data
