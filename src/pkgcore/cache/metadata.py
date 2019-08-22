"""
cache backend designed for rsynced tree's pregenerated metadata.
"""

__all__ = ("database", "protective_database")

import os

from snakeoil.osutils import pjoin
from snakeoil.mappings import ProtectedDict

from pkgcore.cache import flat_hash, errors
from pkgcore.config.hint import ConfigHint
from pkgcore.ebuild import eclass_cache


# store the current key order *here*.
class database(flat_hash.database):
    """Compatibility with (older) portage-generated caches.

    Autodetects per entry if it is a
    :class:`flat_hash.database` or PMS compliant cache entry,
    and converts old (and incomplete) INHERITED field
    to _eclasses_ as required.
    """

    pkgcore_config_type = ConfigHint(
        {'readonly': 'bool', 'location': 'str', 'label': 'str',
         'eclasses': 'ref:eclass_cache'},
        required=['location'],
        positional=['location'],
        typename='cache')

    # No eclass validation data is stored.
    eclass_chf_types = []
    eclass_splitter = ' '
    chf_type = 'mtime'
    complete_eclass_entries = True

    auxdbkeys_order = (
        'DEPEND', 'RDEPEND', 'SLOT', 'SRC_URI',
        'RESTRICT', 'HOMEPAGE',  'LICENSE', 'DESCRIPTION',
        'KEYWORDS', '_eclasses_', 'IUSE', 'REQUIRED_USE',
        'PDEPEND', 'BDEPEND', 'EAPI', 'PROPERTIES',
        'DEFINED_PHASES',
    )

    # this is the old cache format, flat_list.  hardcoded, and must
    # remain that way.
    magic_line_count = 22

    autocommits = True

    def __init__(self, location, *args, **config):
        self.ec = config.pop("eclasses", None)
        if self.ec is None:
            self.ec = eclass_cache.cache(pjoin(location, "eclass"), location)

        config.pop('label', None)
        self.mtime_in_entry = config.pop('mtime_in_entry', True)
        location = pjoin(location, 'metadata', 'cache')
        super().__init__(location, *args, **config)
        self.hardcoded_auxdbkeys_order = tuple(
            (idx, key)
            for idx, key in enumerate(self.auxdbkeys_order)
            if key in self._known_keys)
        self.hardcoded_auxdbkeys_processing = tuple(
            (key in self._known_keys and key or None)
            for key in self.auxdbkeys_order)

    __init__.__doc__ = flat_hash.database.__init__.__doc__.replace(
        "@keyword location", "@param location")

    def _parse_data(self, data, mtime):
        i = iter(self.hardcoded_auxdbkeys_processing)
        d = self._cdict_kls([(key, val) for (key, val) in zip(i, data) if key])
        # sadly, this is faster then doing a .next() and snagging the
        # exception
        for x in i:
            # if we reach here, then bad things occurred.
            raise errors.GeneralCacheCorruption(
                "wrong line count, requires %i" %
                (self.magic_line_count,))

        if self._mtime_used:  # and not self.mtime_in_entry:
            d["_mtime_"] = int(mtime)
        return d

    def _setitem(self, cpv, values):
        values = ProtectedDict(values)

        # hack. proper solution is to make this a __setitem__ override, since
        # template.__setitem__ serializes _eclasses_, then we reconstruct it.
        eclasses = values.pop('_eclasses_', None)
        if eclasses is not None:
            eclasses = self.reconstruct_eclasses(cpv, eclasses)
            values["INHERITED"] = ' '.join(eclasses)

        s = cpv.rfind('/')
        fp = pjoin(self.location, cpv[:s], f'.update.{os.getpid()}.{cpv[s+1:]}')
        try:
            myf = open(fp, "w")
        except FileNotFoundError:
            try:
                self._ensure_dirs(cpv)
                myf = open(fp, "w")
            except EnvironmentError as e:
                raise errors.CacheCorruption(cpv, e) from e
        except EnvironmentError as e:
            raise errors.CacheCorruption(cpv, e) from e

        count = 0
        for idx, key in self.hardcoded_auxdbkeys_order:
            myf.write("%s%s" % ("\n" * (idx - count), values.get(key, "")))
            count = idx
        myf.write("\n" * (self.magic_line_count - count))

        myf.close()
        self._set_mtime(fp, values, eclasses)

        # update written, now we move it
        new_fp = pjoin(self.location, cpv)
        try:
            os.rename(fp, new_fp)
        except EnvironmentError as e:
            os.remove(fp)
            raise errors.CacheCorruption(cpv, e) from e

    def _set_mtime(self, fp, values, eclasses):
        if self._mtime_used:
            self._ensure_access(fp, mtime=values["_mtime_"])


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
