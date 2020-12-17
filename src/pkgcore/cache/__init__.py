"""
cache subsystem, typically used for storing package metadata
"""

__all__ = ("base", "bulk")

import math
import operator
import os
from functools import partial

from snakeoil import klass
from snakeoil.chksum import get_handler
from snakeoil.mappings import ProtectedDict

from ..ebuild.const import metadata_keys
from . import errors


class base:
    # this is for metadata/cache transfer.
    # basically flags the cache needs be updated when transfered cache to cache.
    # leave this.

    """
    :ivar autocommits: Controls whether the template commits every update,
        or queues up updates.
    :ivar cleanse_keys: Boolean controlling whether the template should drop
        empty keys for storing.
    """

    autocommits = False
    cleanse_keys = False
    default_sync_rate = 1
    chf_type = 'mtime'
    eclass_chf_types = ('mtime',)
    eclass_splitter = '\t'

    default_keys = metadata_keys

    frozen = klass.alias_attr('readonly')

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
        self._chf_key = '_%s_' % self.chf_type
        self._chf_serializer = self._get_chf_serializer(self.chf_type)
        self._chf_deserializer = self._get_chf_deserializer(self.chf_type)
        self._known_keys |= frozenset([self._chf_key])
        self._cdict_kls = dict
        self.readonly = readonly
        self.set_sync_rate(self.default_sync_rate)
        self.updates = 0

    @staticmethod
    def _eclassdir_serializer(data):
        return os.path.dirname(data.path)

    @staticmethod
    def _mtime_serializer(data):
        return '%.0f' % math.floor(data.mtime)

    @staticmethod
    def _default_serializer(chf, data):
        # Skip the leading 0x...
        getter = operator.attrgetter(chf)
        return get_handler(chf).long2str(getter(data))

    def _get_chf_serializer(self, chf):
        if chf == 'eclassdir':
            return self._eclassdir_serializer
        if chf == 'mtime':
            return self._mtime_serializer
        return partial(self._default_serializer, chf)

    @staticmethod
    def _mtime_deserializer(data):
        return int(math.floor(float(data)))

    @staticmethod
    def _default_deserializer(data):
        return int(data, 16)

    def _get_chf_deserializer(self, chf):
        if chf == 'eclassdir':
            return str
        elif chf == 'mtime':
            return self._mtime_deserializer
        return self._default_deserializer

    @klass.jit_attr
    def eclass_chf_serializers(self):
        return tuple(self._get_chf_serializer(chf) for chf in
                     self.eclass_chf_types)

    @klass.jit_attr
    def eclass_chf_deserializers(self):
        l = []
        for chf in self.eclass_chf_types:
            l.append((chf, self._get_chf_deserializer(chf)))
        return tuple(l)

    def _sync_if_needed(self, increment=False):
        if self.autocommits:
            return
        if increment:
            self.updates += 1
        if self.updates >= self.sync_rate:
            self.commit()
            self.updates = 0

    def __getitem__(self, cpv):
        """set a cpv to values

        This shouldn't be overridden in derived classes since it
        handles the __eclasses__ conversion. That said, if the class
        handles it, they can override it.
        """
        self._sync_if_needed()
        d = self._getitem(cpv)
        if "_eclasses_" in d:
            d["_eclasses_"] = self.reconstruct_eclasses(cpv, d["_eclasses_"])
        return d

    def _getitem(self, cpv):
        """get cpv's values.

        override this in derived classess.
        """
        raise NotImplementedError

    def __setitem__(self, cpv, values):
        """set a cpv to values

        This shouldn't be overridden in derived classes since it
        handles the readonly checks.
        """
        if self.readonly:
            raise errors.ReadOnly()
        d = ProtectedDict(values)
        if self.cleanse_keys:
            for k in d.keys():
                if not d[k]:
                    del d[k]
            if "_eclasses_" in values:
                d["_eclasses_"] = self.deconstruct_eclasses(d["_eclasses_"])
        elif "_eclasses_" in values:
            d["_eclasses_"] = self.deconstruct_eclasses(d["_eclasses_"])

        d[self._chf_key] = self._chf_serializer(d.pop('_chf_'))
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

        This shouldn't be overridden in derived classes since it
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
        raise NotImplementedError

    def __iter__(self):
        return self.keys()

    def items(self):
        for x in self.keys():
            yield (x, self[x])

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

    def deconstruct_eclasses(self, eclass_dict):
        """takes a dict, returns a string representing said dict"""
        l = []
        converters = self.eclass_chf_serializers
        for eclass, data in eclass_dict.items():
            l.append(eclass)
            l.extend(f(data) for f in converters)
        return self.eclass_splitter.join(l)

    def _deserialize_eclass_chfs(self, data):
        data = zip(self.eclass_chf_deserializers, data)
        for (chf, convert), item in data:
            yield chf, convert(item)

    def reconstruct_eclasses(self, cpv, eclass_string):
        """Turn a string from :obj:`serialize_eclasses` into a dict."""
        if not isinstance(eclass_string, str):
            raise TypeError("eclass_string must be basestring, got %r" %
                eclass_string)
        eclass_data = eclass_string.strip().split(self.eclass_splitter)
        if eclass_data == [""]:
            # occasionally this occurs in the fs backends.  they suck.
            return []

        l = len(eclass_data)
        chf_funcs = self.eclass_chf_deserializers
        tuple_len = len(chf_funcs) + 1
        if len(eclass_data) % tuple_len:
            raise errors.CacheCorruption(
                cpv, f'_eclasses_ was of invalid len {len(eclass_data)}'
                f'(must be mod {tuple_len})'
            )

        i = iter(eclass_data)
        # roughly; deserializer grabs the values it needs, resulting
        # in a sequence of key/tuple pairs for each block of chfs;
        # this is in turn fed into the dict kls which converts it
        # to the dict.
        # Finally, the first item, and that chain, is zipped into
        # a dict; in effect, if 2 chfs, this results in a stream of-
        # (eclass_name, ((chf1,chf1_val), (chf2, chf2_val))).
        try:
            return [(eclass, tuple(self._deserialize_eclass_chfs(i)))
                for eclass in i]
        except ValueError as e:
            raise errors.CacheCorruption(
                cpv, f'ValueError reading {eclass_string!r}') from e

    def validate_entry(self, cache_item, ebuild_hash_item, eclass_db):
        chf_hash = cache_item.get(self._chf_key)
        if (chf_hash is None or
            chf_hash != getattr(ebuild_hash_item, self.chf_type, None)):
            return False
        eclass_data = cache_item.get('_eclasses_')
        if eclass_data is None:
            return True
        update = eclass_db.rebuild_cache_entry(eclass_data)
        if update is None:
            return False
        cache_item['_eclasses_'] = update
        return True


class bulk(base):

    default_sync_rate = 100

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
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

    def _setitem(self, key, val):
        known = self._known_keys
        val = self._cdict_kls((k, v) for k,v in val.items() if k in known)
        self._pending_updates.append((key, val))
        self.data[key] = val

    def _delitem(self, key):
        del self.data[key]
        self._pending_updates.append((key, None))

    def commit(self, force=False):
        if self._pending_updates or force:
            self._write_data()
            self._pending_updates = []
