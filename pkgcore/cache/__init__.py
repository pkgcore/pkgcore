# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
cache subsystem, typically used for storing package metadata
"""

__all__ = ("base", "bulk")

from pkgcore.cache import errors
from snakeoil.mappings import ProtectedDict, autoconvert_py3k_methods_metaclass
from snakeoil.obj import make_SlottedDict_kls
from snakeoil import klass
from snakeoil.compatibility import raise_from

# temp hack for .2
from pkgcore.ebuild.const import metadata_keys
metadata_keys = tuple(metadata_keys)


class base(object):
    # this is for metadata/cache transfer.
    # basically flags the cache needs be updated when transfered cache to cache.
    # leave this.

    """
    @ivar autocommits: Controls whether the template commits every update,
        or queues up updates.
    @ivar complete_eclass_entries: Specifies if the cache backend stores full
        eclass data, or partial.
    @ivar cleanse_keys: Boolean controlling whether the template should drop
        empty keys for storing.
    @ivar serialize_eclasses: Boolean controlling whether the template should
        serialize eclass data itself, or leave it to the derivative.
    """

    complete_eclass_entries = True
    autocommits = False
    cleanse_keys = False
    serialize_eclasses = True
    default_sync_rate = 1

    default_keys = metadata_keys

    frozen = klass.alias_attr('readonly')

    __metaclass__ = autoconvert_py3k_methods_metaclass

    def __init__(self, auxdbkeys=None, readonly=False):
        """
        initialize the derived class; specifically, store label/keys

        :param auxdbkeys: sequence of allowed keys for each cache entry
        :param readonly: defaults to False,
            controls whether the cache is mutable.
        """
        if auxdbkeys is None:
            auxdbkeys = self.default_keys
        self._known_keys = frozenset(auxdbkeys)
        self._cdict_kls = make_SlottedDict_kls(self._known_keys)
        self.readonly = readonly
        self.set_sync_rate(self.default_sync_rate)
        self.updates = 0

    def _sync_if_needed(self, increment=False):
        if self.autocommits:
            return
        if increment:
            self.updates += 1
        if self.updates > self.sync_rate:
            import pdb;pdb.set_trace()
            self.commit()
            self.updates = 0

    def __getitem__(self, cpv):
        """set a cpv to values

        This shouldn't be overriden in derived classes since it
        handles the __eclasses__ conversion. That said, if the class
        handles it, they can override it.
        """
        self._sync_if_needed()
        d = self._getitem(cpv)
        if self.serialize_eclasses and "_eclasses_" in d:
            d["_eclasses_"] = self.reconstruct_eclasses(cpv, d["_eclasses_"])
        return d

    def _getitem(self, cpv):
        """get cpv's values.

        override this in derived classess.
        """
        raise NotImplementedError

    def __setitem__(self, cpv, values):
        """set a cpv to values

        This shouldn't be overriden in derived classes since it
        handles the readonly checks.
        """
        if self.readonly:
            raise errors.ReadOnly()
        if self.cleanse_keys:
            d = ProtectedDict(values)
            for k in d.iterkeys():
                if not d[k]:
                    del d[k]
            if self.serialize_eclasses and "_eclasses_" in values:
                d["_eclasses_"] = self.deconstruct_eclasses(d["_eclasses_"])
        elif self.serialize_eclasses and "_eclasses_" in values:
            d = ProtectedDict(values)
            d["_eclasses_"] = self.deconstruct_eclasses(d["_eclasses_"])
        else:
            d = values
        self._setitem(cpv, d)
        self._sync_if_needed(True)

    def _setitem(self, name, values):
        """__setitem__ calls this after readonly checks.

        override it in derived classes.
        note _eclasses_ key *must* be handled.
        """
        raise NotImplementedError

    def __delitem__(self, cpv):
        """delete a key from the cache.

        This shouldn't be overriden in derived classes since it
        handles the readonly checks.
        """
        if self.readonly:
            raise errors.ReadOnly()
        self._delitem(cpv)
        self._sync_if_needed(True)

    def _delitem(self, cpv):
        """__delitem__ calls this after readonly checks.

        override it in derived classes.
        """
        raise NotImplementedError

    def __contains__(self, cpv):
        raise NotImplementedError

    def has_key(self, cpv):
        return cpv in self

    def keys(self):
        return list(self.iterkeys())

    def iterkeys(self):
        raise NotImplementedError

    def __iter__(self):
        return self.iterkeys()

    def iteritems(self):
        for x in self.iterkeys():
            yield (x, self[x])

    def items(self):
        return list(self.iteritems())

    def clear(self):
        for key in list(self):
            del self[key]

    def set_sync_rate(self, rate=0):
        self.sync_rate = rate
        if rate == 0:
            self.commit()

    def commit(self, force=False):
        if not self.autocommits:
            raise NotImplementedError

    @staticmethod
    def deconstruct_eclasses(eclass_dict):
        """takes a dict, returns a string representing said dict"""
        return "\t".join(
            "%s\t%s\t%s" % (k, v[0], v[1])
            for k, v in eclass_dict.iteritems())

    @staticmethod
    def reconstruct_eclasses(cpv, eclass_string):
        """Turn a string from :obj:`serialize_eclasses` into a dict."""
        if not isinstance(eclass_string, basestring):
            raise TypeError("eclass_string must be basestring, got %r" %
                eclass_string)
        eclasses = eclass_string.strip().split("\t")
        if eclasses == [""]:
            # occasionally this occurs in the fs backends.  they suck.
            return {}

        l = len(eclasses)
        if not l % 3:
            paths = True
        elif not l % 2:
            # edge case of a multiple of 6
            paths = not eclasses[1].isdigit()
        else:
            raise errors.CacheCorruption(
                cpv, "_eclasses_ was of invalid len %i"
                "(must be mod 3 or mod 2)" % len(eclasses))
        d = {}
        try:
            if paths:
                for x in xrange(0, len(eclasses), 3):
                    d[eclasses[x]] = (eclasses[x + 1], long(eclasses[x + 2]))
            else:
                for x in xrange(0, len(eclasses), 2):
                    d[eclasses[x]] = ('', long(eclasses[x + 1]))
        except ValueError:
            raise_from(errors.CacheCorruption(
                cpv, 'ValueError reading %r' % (eclass_string,)))
        return d


class bulk(base):

    default_sync_rate = 100

    def __init__(self, *args, **kwds):
        base.__init__(self, *args, **kwds)
        self._pending_updates = []

    @klass.jit_attr
    def data(self):
        return self._read_data()

    def _read_data(self):
        raise NotImplementedError(self, '_read_data')

    def _write_data(self):
        raise NotImplementedError(self, '_write_data')

    def __contains__(self, key):
        return key in self.data

    def _getitem(self, key):
        return self.data[key]

    def iterkeys(self):
        return self.data.iterkeys()

    def iteritems(self):
        return self.data.iteritems()

    def _setitem(self, key, val):
        known = self._known_keys
        val = self._cdict_kls((k, v) for k,v in val.iteritems() if k in known)
        self._pending_updates.append((key, val))
        self.data[key] = val

    def _delitem(self, key):
        del self.data[key]
        self._pending_updates.append((key, None))

    def commit(self, force=False):
        if self._pending_updates or force:
            self._write_data()
            self._pending_updates = []
