"""
remote binpkg support

Currently this primarily just holds the Packages cache used for remote, and
local binpkg repositories
"""

__all__ = ("PackagesCacheV0", "PackagesCacheV1")

import os
from operator import itemgetter
from time import time

from snakeoil.chksum import get_chksums
from snakeoil.containers import RefCountingSet
from snakeoil.fileutils import AtomicWriteFile, readlines
from snakeoil.mappings import ImmutableDict, StackedDict

from .. import cache
from ..log import logger
from ..restrictions import packages


def _iter_till_empty_newline(data):
    for x in data:
        if not x:
            return
        k, v = x.split(':', 1)
        yield k, v.strip()


class CacheEntry(StackedDict):
    """Customized version of StackedDict blocking pop from modifying the target.

    Note that this pop doesn't through KeyError if something is missing- just
    returns None instead. This is likely to be changed.
    """
    def pop(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


def find_best_savings(stream, line_prefix):
    rcs = RefCountingSet(stream)
    line_overhead = len(line_prefix)
    stream = ((k, v) for k, v in rcs.items() if v != 1)
    return max(stream, key=lambda x: (len(x[0]) + line_overhead) * x[1])[0]


class PackagesCacheV0(cache.bulk):
    """Cache backend for writing binpkg Packages caches

    Note this follows version 0 semantics- not the most efficient, and
    doesn't bundle certain useful keys like RESTRICT
    """

    _header_mangling_map = ImmutableDict({
        'FEATURES': 'UPSTREAM_FEATURES',
        'ACCEPT_KEYWORDS': 'KEYWORDS',
    })

    # this maps from literal keys in the cache to .data[key] expected forms
    _deserialize_map = {
        'DESC': 'DESCRIPTION',
        'MTIME': 'mtime',
        'repo': 'REPO',
    }
    # this maps from .attr to data items.
    _serialize_map = {
        'DESCRIPTION': 'DESC',
        'mtime': 'MTIME',
        'source_repository': 'REPO',
    }
    deserialized_inheritable = frozenset(('CBUILD', 'CHOST', 'source_repository'))
    _pkg_attr_sequences = ('use', 'keywords', 'iuse')
    _deserialized_defaults = dict.fromkeys(
        (
            'BDEPEND', 'DEPEND', 'RDEPEND', 'PDEPEND',
            'BUILD_TIME', 'IUSE', 'KEYWORDS', 'LICENSE', 'PATH', 'PROPERTIES',
            'USE', 'DEFINED_PHASES', 'CHOST', 'CBUILD', 'DESC', 'REPO',
            'DESCRIPTION',
        ),
        ''
    )
    _deserialized_defaults.update({'EAPI': '0', 'SLOT': '0'})
    _deserialized_defaults = ImmutableDict(_deserialized_defaults)

    _stored_chfs = ('size', 'sha1', 'md5', 'mtime')

    version = 0

    def __init__(self, location, *args, **kwds):
        self._location = location
        vkeys = {'CPV'}
        vkeys.update(self._deserialized_defaults)
        vkeys.update(x.upper() for x in self._stored_chfs)
        kwds["auxdbkeys"] = vkeys
        super().__init__(*args, **kwds)

    def _handle(self):
        return readlines(self._location, True, False, False)

    def read_preamble(self, handle):
        return ImmutableDict(
            (self._header_mangling_map.get(k, k), v)
            for k, v in _iter_till_empty_newline(handle))

    def _read_data(self):
        try:
            handle = self._handle()
        except FileNotFoundError:
            return {}
        self.preamble = self.read_preamble(handle)

        defaults = dict(self._deserialized_defaults.items())
        defaults.update((k, v) for k, v in self.preamble.items()
                        if k in self.deserialized_inheritable)
        defaults = ImmutableDict(defaults)

        pkgs = {}
        count = 0
        vkeys = self._known_keys
        while True:
            raw_d = dict(_iter_till_empty_newline(handle))

            d = {k: v for k, v in raw_d.items() if k in vkeys}
            if not d:
                break
            count += 1
            cpv = d.pop("CPV", None)
            if cpv is None:
                cpv = f"{d.pop('CATEGORY')}/{d.pop('PF')}"

            if 'USE' in d:
                d.setdefault('IUSE', d.get('USE', ''))
            for src, dst in self._deserialize_map.items():
                if src in d:
                    d.setdefault(dst, d.pop(src))

            pkgs[cpv] = CacheEntry(d, defaults)
        assert count == int(self.preamble.get('PACKAGES', count))
        return pkgs

    @classmethod
    def _assemble_preamble_dict(cls, target_dicts):
        preamble = {
            'VERSION': cls.version,
            'PACKAGES': len(target_dicts),
            'TIMESTAMP': str(int(time())),
        }
        for key in cls.deserialized_inheritable:
            try:
                preamble[key] = find_best_savings(
                    (d[1].get(key, '') for d in target_dicts), key)
            except ValueError:
                # empty iterable handed to max
                pass
        return preamble

    @classmethod
    def _assemble_pkg_dict(cls, pkg):
        d = {}
        sequences = cls._pkg_attr_sequences
        for key in cls._stored_attrs:

            value = getattr(pkg, key)
            if key in sequences:
                value = ' '.join(sorted(value))
            else:
                value = str(getattr(pkg, key)).strip()
            key = key.upper()
            d[cls._serialize_map.get(key, key)] = value

        for key, value in zip(cls._stored_chfs,
                               get_chksums(pkg.path, *cls._stored_chfs)):
            if key != 'size':
                value = "%x" % (value,)
            d[key.upper()] = value
        d["MTIME"] = str(os.stat(pkg.path).st_mtime)
        return d

    def _write_data(self):
        handler = None
        try:
            try:
                handler = AtomicWriteFile(self._location)
                self._serialize_to_handle(list(self.data.items()), handler)
                handler.close()
            except PermissionError as e:
                logger.error(
                    f'failed writing binpkg cache to {self._location!r}: {e}')
        finally:
            if handler is not None:
                handler.discard()

    def _serialize_to_handle(self, data, handler):
        preamble = self._assemble_preamble_dict(data)

        convert_key = self._serialize_map.get

        for key in sorted(preamble):
            handler.write(f"{convert_key(key, key)}: {preamble[key]}\n")
        handler.write('\n')

        spacer = ' '
        if self.version != 0:
            spacer = ''

        vkeys = self._known_keys
        for cpv, pkg_data in sorted(data, key=itemgetter(0)):
            handler.write(f"CPV:{spacer}{cpv}\n")
            data = [(convert_key(key, key), value)
                    for key, value in pkg_data.items()]
            for write_key, value in sorted(data):
                if write_key not in vkeys:
                    continue
                value = str(value).strip()
                if write_key in preamble:
                    if value != preamble[write_key]:
                        if value:
                            handler.write(f"{write_key}:{spacer}{value}\n")
                        else:
                            handler.write(f"{write_key}:\n")
                elif value:
                    handler.write(f"{write_key}:{spacer}{value}\n")
            handler.write('\n')

    def update_from_xpak(self, pkg, xpak):
        # invert the lookups here; if you do .items() on an xpak,
        # it'll load up the contents in full.
        new_dict = {k: xpak[k] for k in self._known_keys if k in xpak}
        new_dict['_chf_'] = xpak._chf_
        chfs = [x for x in self._stored_chfs if x != 'mtime']
        for key, value in zip(chfs, get_chksums(pkg.path, *chfs)):
            if key != 'size':
                value = "%x" % (value,)
            new_dict[key.upper()] = value
        self[pkg.cpvstr] = new_dict
        return new_dict

    def update_from_repo(self, repo):
        # try to collapse certain keys down to the profile preamble
        targets = repo.match(packages.AlwaysTrue, sorter=sorted)

        if not targets:
            # just open/trunc the target instead, and bail
            open(self._location, 'wb').close()
            return


class PackagesCacheV1(PackagesCacheV0):
    """Cache backend for writing binpkg Packages caches in format version 1.

    See :py:class:`PackagesCacheV0` for usage information; this just writes
    a better ondisk format.
    """

    deserialized_inheritable = PackagesCacheV0.deserialized_inheritable.union(
        ('SLOT', 'EAPI', 'LICENSE', 'KEYWORDS', 'USE', 'RESTRICT'))

    _deserialized_defaults = ImmutableDict(
        list(PackagesCacheV0._deserialized_defaults.items()) + [('RESTRICT', '')])

    @classmethod
    def _assemble_pkg_dict(cls, pkg):
        # not the most efficient...
        d = PackagesCacheV0._assemble_pkg_dict(pkg)
        use = set(pkg.use).intersection(pkg.iuse_stripped)
        d.pop("IUSE", None)
        iuse_bits = [f'-{x}' for x in pkg.iuse_stripped if x not in use]
        use.update(iuse_bits)
        d["USE"] = ' '.join(sorted(use))
        return d

    version = 1


def get_cache_kls(version):
    version = str(version)
    if version == '0':
        return PackagesCacheV0
    elif version in ('1', '-1'):
        return PackagesCacheV1
    raise KeyError(f"cache version {version} unsupported")
