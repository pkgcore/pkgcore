# Copyright: 2005-2006 Brian Harring <ferringb@gmail.com>
# License: GPL2
# $Id:$


"""
collection of container classes
"""

from pkgcore.util.demandload import demandload
demandload(globals(),
    "pkgcore.util.lists:iter_stable_unique "
    "itertools:chain "
)

class InvertedContains(set):

    """Set that inverts all contains lookups results

    Mainly useful in conjuection with LimitedChangeSet for converting
    from blacklist to whitelist.

    Not able to be iterated over also
    """

    def __contains__(self, key):
        return not set.__contains__(self, key)

    def __iter__(self):
        # infinite set, non iterable.
        raise TypeError


class LimitedChangeSet(object):

    """Set used to limit the number of times a key can be removed/added

    specifically deleting/adding a key only once per commit,
    optionally blocking changes to certain keys.
    """

    _removed	= 0
    _added		= 1

    def __init__(self, initial_keys, unchangable_keys=None):
        self._new = set(initial_keys)
        if unchangable_keys is None:
            self._blacklist = []
        else:
            if isinstance(unchangable_keys, (list, tuple)):
                unchangable_keys = set(unchangable_keys)
            self._blacklist = unchangable_keys
        self._changed = set()
        self._change_order = []
        self._orig = frozenset(self._new)

    def add(self, key):
        if key in self._changed or key in self._blacklist:
            # it's been del'd already once upon a time.
            if key in self._new:
                return
            raise Unchangable(key)

        self._new.add(key)
        self._changed.add(key)
        self._change_order.append((self._added, key))

    def remove(self, key):
        if key in self._changed or key in self._blacklist:
            if key not in self._new:
                raise KeyError(key)
            raise Unchangable(key)

        if key in self._new:
            self._new.remove(key)
        self._changed.add(key)
        self._change_order.append((self._removed, key))

    def __contains__(self, key):
        return key in self._new

    def changes_count(self):
        return len(self._change_order)

    def commit(self):
        self._orig = frozenset(self._new)
        self._changed.clear()
        self._change_order = []

    def rollback(self, point=0):
        l = self.changes_count()
        if point < 0 or point > l:
            raise TypeError(
                "%s point must be >=0 and <= changes_count()" % point)
        while l > point:
            change, key = self._change_order.pop(-1)
            self._changed.remove(key)
            if change == self._removed:
                self._new.add(key)
            else:
                self._new.remove(key)
            l -= 1

    def __str__(self):
        return str(self._new).replace("set(", "LimitedChangeSet(", 1)

    def __iter__(self):
        return iter(self._new)

    def __len__(self):
        return len(self._new)

    def __eq__(self, other):
        if isinstance(other, LimitedChangeSet):
            return self._new == other._new
        elif isinstance(other, set):
            return self._new == other
        return False

    def __ne__(self, other):
        return not (self == other)


class Unchangable(Exception):

    def __init__(self, key):
        Exception.__init__(self, "key '%s' is unchangable" % (key,))
        self.key = key


class ProtectedSet(object):

    """
    Wraps a set pushing all changes into a secondary set.

    Be aware that it lacks the majority of set methods.
    """
    def __init__(self, orig_set):
        self._orig = orig_set
        self._new = set()

    def __contains__(self, key):
        return key in self._orig or key in self._new

    def __iter__(self):
        return iter_stable_unique(chain(self._new, self._orig))

    def __len__(self):
        return len(self._orig.union(self._new))

    def add(self, key):
        if key not in self._orig:
            self._new.add(key)


class RefCountingSet(dict):

    def __init__(self, iterable=None):
        if iterable is not None:
            dict.__init__(self, ((x, 1) for x in iterable))

    def add(self, item):
        count = self.get(item, 0)
        self[item] = count + 1

    def remove(self, item):
        count = self[item]
        if count == 1:
            del self[item]
        else:
            self[item] = count - 1
