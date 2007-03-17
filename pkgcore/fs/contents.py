# Copyright: 2005-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
contents set- container of fs objects
"""

from pkgcore.fs import fs
from pkgcore.util.compatibility import all
from pkgcore.util.klass import generic_equality
from pkgcore.util.demandload import demandload
demandload(globals(),
    "pkgcore.fs.ops:offset_rewriter,change_offset_rewriter "
)

def check_instance(obj):
    if not isinstance(obj, fs.fsBase):
        raise TypeError("'%s' is not a fs.fsBase deriviative" % obj)
    return obj.location, obj


class contentsSet(object):
    """set of L{fs<pkgcore.fs.fs>} objects"""

    __metaclass__ = generic_equality
    __attr_comparison__ = ('_dict',)

    def __init__(self, initial=None, mutable=True):

        """
        @param initial: initial fs objs for this set
        @type initial: sequence
        @param mutable: controls if it modifiable after initialization
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

    def discard(self, obj):
        if isinstance(obj, fs.fsBase):
            self._dict.pop(obj.location, None)
        else:
            self._dict.pop(obj, None)

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

    @staticmethod
    def _convert_loc(iterable):
        fs_kls = fs.fsBase
        for x in iterable:
            if isinstance(x, fs_kls):
                yield x.location
            else:
                yield x

    @staticmethod
    def _ensure_fsbase(iterable):
        fs_kls = fs.fsBase
        for x in iterable:
            if not isinstance(x, fs_kls):
                raise ValueError("must be an fsBase derivative: got %r" % x)
            yield x

    def difference(self, other):
        if not hasattr(other, '__contains__'):
            other = set(self._convert_loc(other))
        return contentsSet((x for x in self if x.location not in other),
            mutable=self.mutable)

    def difference_update(self, other):
        if not self.mutable:
            raise TypeError("%r isn't mutable" % self)

        rem = self.remove
        for x in other:
            if x in self:
                rem(x)

    def intersection(self, other):
        return contentsSet((x for x in other if x in self),
            mutable=self.mutable)

    def intersection_update(self, other):
        if not self.mutable:
            raise TypeError("%r isn't mutable" % self)
        if not hasattr(other, '__contains__'):
            other = set(self._convert_loc(other))

        l = []
        for x in self:
            if x.location not in other:
                l.append(x)
        for x in l:
            self.remove(x)

    def issubset(self, other):
        if not hasattr(other, '__contains__'):
            other = set(self._convert_loc(other))
        return all(x.location in other for x in self._dict)

    def issuperset(self, other):
        return all(x in self for x in other)

    def union(self, other):
        c = contentsSet(other)
        c.update(self)
        return c

    def __iter__(self):
        return self._dict.itervalues()

    def __len__(self):
        return len(self._dict)

    def symmetric_difference(self, other):
        c = contentsSet(mutable=True)
        c.update(self)
        c.symmetric_difference_update(other)
        object.__setattr__(c, 'mutable', self.mutable)
        return c

    def symmetric_difference_update(self, other):
        if not self.mutable:
            raise TypeError("%r isn't mutable" % self)
        if not hasattr(other, '__contains__'):
            other = contentsSet(self._ensure_fsbase(other))
        l = []
        for x in self:
            if x in other:
                l.append(x)
        add = self.add
        for x in other:
            if x not in self:
                add(x)
        rem = self.remove
        for x in l:
            rem(x)
        del l, rem

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

    def clone(self, empty=False):
        if empty:
            return self.__class__([], mutable=True)
        return self.__class__(self._dict.itervalues(), mutable=True)

    def insert_offset(self, offset):
        cset = self.clone(empty=True)
        cset.update(offset_rewriter(offset, self))
        return cset            

    def change_offset(self, old_offset, new_offset):
        cset = self.clone(empty=True)
        cset.update(change_offset_rewriter(old_offset, new_offset, self))
        return cset
