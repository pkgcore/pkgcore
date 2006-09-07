# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
contents set- container of fs objects
"""

from pkgcore.fs import fs
from pkgcore.util.compatibility import all
from itertools import chain

def check_instance(obj):
    if not isinstance(obj, fs.fsBase):
        raise TypeError("'%s' is not a fs.fsBase deriviative" % obj)
    return obj.location, obj


class contentsSet(object):
    """set of L{fs<pkgcore.fs.fs>} objects"""

    def __init__(self, initial=None, mutable=False):

        """
        @param initial: initial fs objs for this set
        @type initial: sequence
        @param frozen: controls if it modifiable after initialization
        """
        self._dict = {}
        if initial is not None:
            self._dict.update(check_instance(x) for x in initial)
        self.mutable = mutable

    def add(self, obj):

        """
        add a new fs obj to the set

        @param obj: must be a derivative of L{pkgcore.fs.fs.fsBase}
        """

        if not self.mutable:
            # weird, but keeping with set.
            raise AttributeError(
                "%s is frozen; no add functionality" % self.__class__)
        if not isinstance(obj, fs.fsBase):
            raise TypeError("'%s' is not a fs.fsBase class" % str(obj))
        self._dict[obj.location] = obj

    def __delitem__(self, obj):

        """
        remove a fs obj to the set

        @type obj: a derivative of L{pkgcore.fs.fs.fsBase}
            or a string location of an obj in the set.
        @raise KeyError: if the obj isn't found
        """

        if not self.mutable:
            # weird, but keeping with set.
            raise AttributeError(
                "%s is frozen; no remove functionality" % self.__class__)
        if isinstance(obj, fs.fsBase):
            del self._dict[obj.location]
        else:
            del self._dict[obj]

    def remove(self, obj):
        del self[obj]

    def __eq__(self, other):
        if isinstance(other, contentsSet):
            return self._dict == other._dict
        return False

    def __ne__(self, other):
        if isinstance(other, contentsSet):
            return self._dict != other._dict
        return True

    def __getitem__(self, obj):
        if isinstance(obj, fs.fsBase):
            return self._dict[obj.location]
        return self._dict[obj]

    def __contains__(self, key):
        if isinstance(key, fs.fsBase):
            return key.location in self._dict
        return key in self._dict

    def clear(self):
        """
        clear the set
        @raise ttributeError: if the instance is frozen
        """
        if not self.mutable:
            # weird, but keeping with set.
            raise AttributeError(
                "%s is frozen; no clear functionality" % self.__class__)
        self._dict.clear()

    def difference(self, other):
        if isinstance(other, contentsSet):
            return contentsSet((x for x in self if x.location not in other))
        return set.difference(self, other)

    def intersection(self, other):
        return contentsSet((x for x in self if x.location in other))

    def issubset(self, other):
        return all(x.location in other for x in self._dict)

    def issuperset(self, other):
        if isinstance(other, contentsSet):
            return other.issubset(self)
        return all(x in self for x in other)

    def union(self, other):
        if not isinstance(other, contentsSet):
            raise TypeError(
                "will only do unions with contentsSet derivatives, not %s" %
                other.__class__)

        c = contentsSet(other)
        c.update(self)
        return c

    def __iter__(self):
        return self._dict.itervalues()

    def __len__(self):
        return len(self._dict)

    def symmetric_difference(self, other):
        i = self.intersection(other)
        return contentsSet(chain(iter(self.difference(i)),
                                 iter(other.difference(i))))

    def update(self, iterable):
        self._dict.update((x.location, x) for x in iterable)

    def iterfiles(self, invert=False):
        return (x for x in self if isinstance(x, fs.fsFile) is not invert)

    def files(self, invert=False):
        return list(self.iterfiles(invert=invert))

    def iterdirs(self, invert=False):
        return (x for x in self if isinstance(x, fs.fsDir) is not invert)

    def dirs(self, invert=False):
        return list(self.iterdirs(invert=invert))

    def iterlinks(self, invert=False):
        return (x for x in self if isinstance(x, fs.fsLink) is not invert)

    def links(self, invert=False):
        return list(self.iterlinks(invert=invert))

    def iterdevs(self, invert=False):
        return (x for x in self if isinstance(x, fs.fsDev) is not invert)

    def devs(self, invert=False):
        return list(self.iterdevs(invert=invert))

    def iterfifos(self, invert=False):
        return (x for x in self if isinstance(x, fs.fsFifo) is not invert)

    def fifos(self, invert=False):
        return list(self.iterfifos(invert=invert))

    for k in ("files", "dirs", "links", "devs", "fifos"):
        s = k.capitalize()
        locals()[k].__doc__ = \
            """
            returns a list of just L{pkgcore.fs.fs.fs%s} instances
            @param invert: if True, yield everything that isn't a
                fs%s instance, else yields just fs%s
            """ % (s.rstrip("s"), s, s)
        locals()["iter"+k].__doc__ = \
            """
            a generator yielding just L{pkgcore.fs.fs.fs%s} instances
            @param invert: if True, yield everything that isn't a
                fs%s instance, else yields just fs%s
            """ % (s.rstrip("s"), s, s)
        del s
    del k

    def clone(self, mutable=False):
        if mutable == self.mutable:
            return self
        return self.__class__(self._dict.itervalues(), mutable=mutable)
