# Copyright: 2005-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
in memory representation of on disk eclass stacking order
"""

from snakeoil.data_source import local_source
from pkgcore.config import ConfigHint

from snakeoil.mappings import ImmutableDict
from snakeoil.weakrefs import WeakValCache
from snakeoil.osutils import join as pjoin, listdir_files
from snakeoil.compatibility import intern
from snakeoil.klass import jit_attr_ext_method

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
        # self.eclasses = {} # {"Name": ("location","_mtime_")}
        self.portdir = portdir
        self.eclassdir = eclassdir

    def is_eclass_data_valid(self, ec_dict):
        """Check if eclass data is still valid.

        Given a dict as returned by get_eclass_data, walk it comparing
        it to internal eclass view.

        @return: a boolean representing whether that eclass data is still
            up to date, or not
        """
        ec = self.eclasses
        for eclass, tup in ec_dict.iteritems():
            if eclass not in ec:
                return False
            if tup[1] != ec[eclass][1]:
                return False
        return True

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
        return local_source(pjoin(o[0], eclass+".eclass"))

    eclasses = jit_attr_ext_method("_load_eclasses", "_eclasses")


class cache(base):

    pkgcore_config_type = ConfigHint({"path":"str", "portdir":"str"},
                                     typename='eclass_cache')

    def __init__(self, path, portdir=None):
        """
        @param portdir: ondisk location of the tree we're working with
        """
        base.__init__(self, portdir=portdir, eclassdir=normpath(path))

    def _load_eclasses(self):
        """Force an update of the internal view of on disk/remote eclasses."""
        ec = {}
        eclass_len = len(".eclass")
        try:
            files = listdir_files(self.eclassdir)
        except (OSError, IOError), e:
            if e.errno not in (errno.ENOENT, errno.ENOTDIR):
                raise
            return ImmutableDict()
        for y in files:
            if not y.endswith(".eclass"):
                continue
            mtime = os.stat(pjoin(self.eclassdir, y)).st_mtime
            ys = y[:-eclass_len]
            ec[intern(ys)] = (self.eclassdir, long(mtime))
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
        @param caches: L{cache} instances to stack;
            ordering should be desired lookup order
        @keyword eclassdir: override for the master eclass dir, required for
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
