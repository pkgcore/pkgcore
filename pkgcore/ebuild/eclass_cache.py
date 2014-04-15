# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
in memory representation of on disk eclass stacking order
"""

__all__ = ("base", "cache", "StackedCaches")

import operator

from snakeoil.data_source import local_source
from pkgcore.config import ConfigHint

from snakeoil.chksum import LazilyHashedPath
from snakeoil.compatibility import intern
from snakeoil.klass import jit_attr_ext_method
from snakeoil.mappings import ImmutableDict
from snakeoil.osutils import pjoin, listdir_files
from snakeoil.weakrefs import WeakValCache

from snakeoil.demandload import demandload
demandload(globals(),
    "errno",
    "os",
    "snakeoil.osutils:normpath",
    "snakeoil.mappings:StackedDict",
)

class base(object):
    """
    Maintains the cache information about eclasses available to an ebuild.
    """

    def __init__(self, portdir=None, eclassdir=None):
        self._eclass_data_inst_cache = WeakValCache()
        # generate this.
        # self.eclasses = {} # {"Name": ("location", "_mtime_")}
        self.portdir = portdir
        self.eclassdir = eclassdir

    def get_eclass_data(self, inherits):
        """Return the cachable entries from a list of inherited eclasses.

        Only make get_eclass_data calls for data you know came from
        this eclass_cache, otherwise be ready to catch a KeyError
        exception for any eclass that was requested, but not known to
        this cache.
        """

        keys = tuple(sorted(inherits))
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


class cache(base):

    pkgcore_config_type = ConfigHint({"path":"str", "portdir":"str"},
                                     typename='eclass_cache')

    def __init__(self, path, portdir=None):
        """
        :param portdir: ondisk location of the tree we're working with
        """
        base.__init__(self, portdir=portdir, eclassdir=normpath(path))

    def _load_eclasses(self):
        """Force an update of the internal view of on disk/remote eclasses."""
        ec = {}
        eclass_len = len(".eclass")
        try:
            files = listdir_files(self.eclassdir)
        except EnvironmentError, e:
            if e.errno not in (errno.ENOENT, errno.ENOTDIR):
                raise
            return ImmutableDict()
        for y in files:
            if not y.endswith(".eclass"):
                continue
            ys = y[:-eclass_len]
            ec[intern(ys)] = LazilyHashedPath(pjoin(self.eclassdir, y),
                                              eclassdir=self.eclassdir)
        return ImmutableDict(ec)


class StackedCaches(base):

    """
    collapse multiple eclass caches into one.

    Does L->R searching for eclass matches.
    """

    pkgcore_config_type = ConfigHint(
        {'caches': 'refs:eclass_cache', 'portdir': 'str', 'eclassdir': 'str'},
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
        kwds.setdefault("portdir",
            os.path.dirname(kwds["eclassdir"].rstrip(os.path.sep)))
        self._caches = caches
        base.__init__(self, **kwds)

    def _load_eclasses(self):
        return StackedDict(*[ec.eclasses for ec in self._caches])
