# Copyright: 2005-2010 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""
cache backend designed for rsynced tree's pregenerated metadata.
"""

__all__ = ("database", "paludis_flat_list", "protective_database")

import os
import errno
from itertools import izip
from pkgcore.cache import flat_hash, errors
from pkgcore.config import ConfigHint
from pkgcore.ebuild import eclass_cache
from snakeoil.osutils import join as pjoin
from snakeoil.mappings import ProtectedDict


# store the current key order *here*.
class database(flat_hash.database):
    """
    Compatibility with (older) portage-generated caches.

    Autodetects per entry if it is a
    L{flat_list<pkgcore.cache.flat_hash.database>} and flat_list
    backends entry, and converts old (and incomplete) INHERITED field
    to _eclasses_ as required.
    """

    pkgcore_config_type = ConfigHint(
        {'readonly': 'bool', 'location': 'str', 'label': 'str',
        'eclasses':'ref:eclass_cache'},
        required=['location'],
        positional=['location'],
        typename='cache')


    complete_eclass_entries = False

    auxdbkeys_order = ('DEPEND', 'RDEPEND', 'SLOT', 'SRC_URI',
        'RESTRICT',  'HOMEPAGE',  'LICENSE', 'DESCRIPTION',
        'KEYWORDS',  'INHERITED', 'IUSE', 'CDEPEND',
        'PDEPEND',   'PROVIDE', 'EAPI', 'PROPERTIES',
        'DEFINED_PHASES')

    # this is the old cache format, flat_list.  hardcoded, and must
    # remain that way.
    magic_line_count = 22

    autocommits = True

    def __init__(self, location, *args, **config):
        self.ec = config.pop("eclasses", None)
        if self.ec is None:
            #import pdb;pdb.set_trace()
            self.ec = eclass_cache.cache(pjoin(location, "eclass"), location)

        config.pop('label', None)
        self.mtime_in_entry = config.pop('mtime_in_entry', True)
        location = pjoin(location, 'metadata', 'cache')
        super(database, self).__init__(location, *args, **config)
        self.hardcoded_auxdbkeys_order = tuple((idx, key)
            for idx, key in enumerate(self.auxdbkeys_order)
                if key in self._known_keys)
        self.hardcoded_auxdbkeys_processing = tuple(
            (key in self._known_keys and key or None)
                for key in self.auxdbkeys_order)

    __init__.__doc__ = flat_hash.database.__init__.__doc__.replace(
        "@keyword location", "@param location")


    def _format_location(self):
        return pjoin(self.location, "metadata", "cache")

    def __getitem__(self, cpv):
        d = flat_hash.database.__getitem__(self, cpv)

        if "_eclasses_" not in d:
            if "INHERITED" in d:
                d["_eclasses_"] = self.ec.get_eclass_data(
                    d["INHERITED"].split())
                del d["INHERITED"]
        else:
            d["_eclasses_"] = self.reconstruct_eclasses(cpv, d["_eclasses_"])

        return d

    def _parse_data(self, data, mtime):
        i = iter(self.hardcoded_auxdbkeys_processing)
        d = self._cdict_kls([(key, val) for (key, val) in
            izip(i, data) if key])
        # sadly, this is faster then doing a .next() and snagging the
        # exception
        for x in i:
            # if we reach here, then bad things occured.
            raise errors.GeneralCacheCorruption(
                "wrong line count, requires %i" %
                    (self.magic_line_count,))

        if self._mtime_used: # and not self.mtime_in_entry:
            d["_mtime_"] = long(mtime)
        return d

    def _setitem(self, cpv, values):
        values = ProtectedDict(values)

        # hack. proper solution is to make this a __setitem__ override, since
        # template.__setitem__ serializes _eclasses_, then we reconstruct it.
        eclasses = values.pop('_eclasses_', None)
        if eclasses is not None:
            eclasses = self.reconstruct_eclasses(cpv, eclasses)
            values["INHERITED"] = ' '.join(eclasses)

        s = cpv.rfind("/")
        fp = pjoin(
            self.location, cpv[:s],".update.%i.%s" % (os.getpid(), cpv[s+1:]))
        try:
            myf = open(fp, "w")
        except (OSError, IOError), e:
            if errno.ENOENT == e.errno:
                try:
                    self._ensure_dirs(cpv)
                    myf = open(fp,"w")
                except (OSError, IOError),e:
                    raise errors.CacheCorruption(cpv, e)
            else:
                raise errors.CacheCorruption(cpv, e)

        count = 0
        for idx, key in self.hardcoded_auxdbkeys_order:
            myf.write("%s%s" % ("\n" * (idx - count), values.get(key, "")))
            count = idx
        myf.write("\n" * (self.magic_line_count - count))

        myf.close()
        self._set_mtime(fp, values, eclasses)

        #update written.  now we move it.
        new_fp = pjoin(self.location, cpv)
        try:
            os.rename(fp, new_fp)
        except (OSError, IOError), e:
            os.remove(fp)
            raise errors.CacheCorruption(cpv, e)

    def _set_mtime(self, fp, values, eclasses):
        if self._mtime_used:
            self._ensure_access(fp, mtime=values["_mtime_"])


class paludis_flat_list(database):

    """
    (Hopefully) write a paludis specific form of flat_list format cache.
    Not very well tested.

    difference from a normal flat_list cache is that mtime is set to ebuild
    for normal, for paludis it's max mtime of eclasses/ebuild involved.
    """

    pkgcore_config_type = ConfigHint(
        {'readonly': 'bool', 'location': 'str', 'label': 'str'},
        required=['location'],
        positional=['location'],
        typename='cache')

    def __init__(self, *args, **config):
        config['auxdbkeys'] = self.auxdbkeys_order
        database.__init__(self, *args, **config)

    def _set_mtime(self, fp, values, eclasses):
        mtime = values.get("_mtime_", 0)

        if eclasses:
            self._ensure_access(
                fp,
                mtime=max(max(mtime for path, mtime in eclasses.itervalues()),
                          mtime))
        else:
            self._ensure_access(fp, mtime)


class protective_database(database):

    def _parse_data(self, data, mtime):
        # easy attempt first.
        data = list(data)
        if len(data) != self.magic_line_count:
            return flat_hash.database._parse_data(self, data, mtime)

        # this one's interesting.
        d = self._cdict_kls()

        for line in data:
            # yes, meant to iterate over a string.
            hashed = False
            for idx, c in enumerate(line):
                if not c.isalpha():
                    if c == "=" and idx > 0:
                        hashed = True
                        d[line[:idx]] = line[idx + 1:]
                    elif c == "_" or c.isdigit():
                        continue
                    break
                elif not c.isupper():
                    break

            if not hashed:
                # non hashed.
                d.clear()
                for idx, key in self.hardcoded_auxdbkeys_order:
                    d[key] = data[idx].strip()
                break

        if self._mtime_used:
            d["_mtime_"] = mtime
        return d


