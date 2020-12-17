"""
in memory representation of on disk eclass stacking order
"""

__all__ = ("base", "cache", "StackedCaches")

import os
from sys import intern

from snakeoil.chksum import LazilyHashedPath
from snakeoil.data_source import local_source
from snakeoil.klass import jit_attr_ext_method
from snakeoil.mappings import ImmutableDict, OrderedFrozenSet, StackedDict
from snakeoil.osutils import listdir_files, normpath, pjoin
from snakeoil.weakrefs import WeakValCache

from ..config.hint import ConfigHint


class base:
    """
    Maintains the cache information about eclasses available to an ebuild.
    """

    def __init__(self, location=None, eclassdir=None):
        self._eclass_data_inst_cache = WeakValCache()
        # generate this.
        # self.eclasses = {} # {"Name": ("location", "_mtime_")}
        self.location = location
        self.eclassdir = eclassdir

    def get_eclass_data(self, inherits):
        """Return the cachable entries from a list of inherited eclasses.

        Only make get_eclass_data calls for data you know came from
        this eclass_cache, otherwise be ready to catch a KeyError
        exception for any eclass that was requested, but not known to
        this cache.
        """

        keys = OrderedFrozenSet(inherits)
        o = self._eclass_data_inst_cache.get(keys)
        if o is None:
            o = ImmutableDict((k, self.eclasses[k]) for k in keys)
            self._eclass_data_inst_cache[keys] = o
        return o

    def get_eclass(self, eclass):
        o = self.eclasses.get(eclass)
        if o is None:
            return None
        return local_source(o.path)

    eclasses = jit_attr_ext_method("_load_eclasses", "_eclasses")

    def rebuild_cache_entry(self, entry_eclasses):
        """Check if eclass data is still valid.

        Given a dict as returned by get_eclass_data, walk it comparing
        it to internal eclass view.

        :return: a boolean representing whether that eclass data is still
            up to date, or not
        """
        ec = self.eclasses
        d = {}

        for eclass, chksums in entry_eclasses:
            data = ec.get(eclass)
            if any(val != getattr(data, chf, None) for chf, val in chksums):
                return None
            d[eclass] = data

        return d

    def __getstate__(self):
        d = self.__dict__.copy()
        del d['_eclass_data_inst_cache']
        return d

    def __setstate__(self, state):
        self.__dict__ = state.copy()
        self.__dict__['_eclass_data_inst_cache'] = WeakValCache()


class cache(base):

    pkgcore_config_type = ConfigHint({"path":"str", "location":"str"},
                                     typename='eclass_cache')

    def __init__(self, path, location=None):
        """
        :param location: ondisk location of the tree we're working with
        """
        base.__init__(self, location=location, eclassdir=normpath(path))

    def _load_eclasses(self):
        """Force an update of the internal view of on disk/remote eclasses."""
        ec = {}
        eclass_len = len(".eclass")
        try:
            files = listdir_files(self.eclassdir)
        except (FileNotFoundError, NotADirectoryError):
            return ImmutableDict()
        for y in sorted(files):
            if not y.endswith(".eclass"):
                continue
            ys = y[:-eclass_len]
            ec[intern(ys)] = LazilyHashedPath(
                pjoin(self.eclassdir, y), eclassdir=self.eclassdir)
        return ImmutableDict(ec)


class StackedCaches(base):

    """
    collapse multiple eclass caches into one.

    Does L->R searching for eclass matches.
    """

    pkgcore_config_type = ConfigHint(
        {'caches': 'refs:eclass_cache', 'location': 'str', 'eclassdir': 'str'},
        typename='eclass_cache')

    def __init__(self, caches, **kwds):
        """
        :param caches: :obj:`cache` instances to stack;
            ordering should be desired lookup order
        :keyword eclassdir: override for the master eclass dir, required for
            eapi0 and idiot eclass usage.  defaults to pulling from the first
            cache.
        """
        if len(caches) < 2:
            raise TypeError(
                "%s requires at least two eclass_caches" % self.__class__)

        kwds.setdefault("eclassdir", caches[0].eclassdir)
        kwds.setdefault("location", os.path.dirname(kwds["eclassdir"].rstrip(os.path.sep)))
        self._caches = caches
        base.__init__(self, **kwds)

    def _load_eclasses(self):
        return StackedDict(*[ec.eclasses for ec in self._caches])
