# Copyright: 2008-2009 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from snakeoil.mappings import ImmutableDict, StackedDict
from snakeoil.containers import RefCountingSet
from snakeoil.fileutils import AtomicWriteFile
from snakeoil import klass
from snakeoil.compatibility import all
from pkgcore.ebuild.cpv import versioned_CPV
from pkgcore.restrictions.packages import AlwaysTrue
from pkgcore.chksum import get_chksums
from operator import itemgetter, attrgetter
from itertools import izip
from pkgcore import cache
import os

def iter_till_empty_newline(data):
    for x in data:
        x = x.strip()
        if not x:
            return
        k, v = x.split(':', 1)
        yield k.strip(), v.strip()


class CacheEntry(StackedDict):

    def pop(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

def find_best_savings(stream, line_prefix):
    rcs = RefCountingSet(stream)
    line_overhead = len(line_prefix)
    stream = ((k, v) for k,v in rcs.iteritems() if v != 1)
    return max(stream, key=lambda (k, v):(len(k) + line_overhead) * v)[0]


class PackagesCacheV0(cache.bulk):

    _header_mangling_map = ImmutableDict({
        'FEATURES':'UPSTREAM_FEATURES',
        'ACCEPT_KEYWORDS':'KEYWORDS'})

    _rewrite_map = {'DESC':'DESCRIPTION', 'repo':'repository'}
    _write_translate = {"DEPENDS": "DEPEND", "RDEPENDS": "RDEPEND",
        "POST_RDEPENDS":"POST_RDEPEND", "DESCRIPTION":"DESC"}
    inheritable = frozenset(('USE', 'CBUILD', 'CHOST', 'repository'))
    _sequences = ('use', 'keywords', 'iuse')
    _pkg_defaults = dict.fromkeys(('BUILD_TIME', 'DEPEND', 'IUSE', 'KEYWORDS',
        'LICENSE', 'PATH', 'PDEPEND', 'PROPERTIES', 'PROVIDE', 'RDEPEND',
        'RESTRICT', 'USE', 'DEFINED_PHASES', 'CHOST', 'CBUILD', 'DESC', 'repo'),
        '')
    _pkg_defaults.update({'EAPI':'0', 'SLOT':'0'})
    _pkg_defaults = ImmutableDict(_pkg_defaults)

    _stored_chfs = ('size', 'sha1', 'md5', 'mtime')

    version = 0

    def __init__(self, location, *args, **kwds):
        self._location = location
        cache.bulk.__init__(self, *args, **kwds)
        vkeys = set(self._stored_chfs)
        vkeys.update(self._pkg_defaults)
        vkeys.add("CPV")
        vkeys.update(x.upper() for x in self._stored_chfs)
        self._valid_keys = frozenset(vkeys)

    def _handle(self):
        return iter(open(self._location))

    def read_preamble(self, handle):
        return ImmutableDict(
            (self._header_mangling_map.get(k, k), v)
            for k,v in iter_till_empty_newline(handle))

    def _read_data(self):
        handle = self._handle()
        preamble = self.preamble = self.read_preamble(handle)

        pkgs = {}
        count = 0
        vkeys = self._valid_keys
        while True:
            raw_d = dict(iter_till_empty_newline(handle))

            d = dict((k, v) for k,v in raw_d.iteritems() if k in vkeys)
            if not d:
                break
            count += 1
            cpv = d.pop("CPV", None)
            if cpv is None:
                cpv = "%s/%s" % (d.pop("CATEGORY"), d.pop("PF"))

            d.setdefault('IUSE', d.get('USE', ''))
            for src, dst in self._rewrite_map.iteritems():
                d.setdefault(dst, d.pop(src, ''))

            pkgs[cpv] = CacheEntry(d, preamble)
        assert count == int(preamble.get('PACKAGES', count))
        return pkgs

    @classmethod
    def _assemble_preamble_dict(cls, target_dicts):
        preamble = {'VERSION':cls.version, 'PACKAGES':len(target_dicts)}
        for key in cls.inheritable:
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
        sequences = cls._sequences
        for key in cls._stored_attrs:

            value = getattr(pkg, key)
            if key in sequences:
                value = ' '.join(sorted(value))
            else:
                value = str(getattr(pkg, key)).strip()
            key = key.upper()
            d[cls._write_translate.get(key, key)] = value

        for key, value in izip(cls._stored_chfs,
            get_chksums(pkg.path, *cls._stored_chfs)):
            if key != 'size':
                value = "%x" % (value,)
            d[key.upper()] = value
        d["MTIME"] = str(os.stat(pkg.path).st_mtime)
        return d

    def _write_data(self):
        handler = AtomicWriteFile(self._location)
        try:
            self._serialize_to_handle(self.data.items(), handler)
            handler.close()
        except:
            handler.discard()
            raise

    def _serialize_to_handle(self, data, handler):
#        data = [self._assemble_pkg_dict(pkg) for pkg in targets]
        preamble = self._assemble_preamble_dict(data)

        for key in sorted(preamble):
            handler.write("%s: %s\n" % (key, preamble[key]))
        handler.write('\n')

        spacer = ' '
        if self.version != 0:
            spacer = ''

        vkeys = self._valid_keys
        for cpv, pkg_data in sorted(data, key=itemgetter(0)):
            handler.write("CPV:%s%s\n" % (spacer, cpv))
            for key in sorted(pkg_data):
                write_key = self._write_translate.get(key, key)
                if write_key not in vkeys:
                    continue
                value = pkg_data[key]
                if write_key in preamble:
                    if value != preamble[write_key]:
                        if value:
                            handler.write("%s:%s%s\n" % (write_key, spacer, value))
                        else:
                            handler.write("%s:\n" % (write_key,))
                elif value:
                    handler.write("%s:%s%s\n" % (write_key, spacer, value))
            handler.write('\n')

    def update_from_repo(self, repo):
        # try to collapse certain keys down to the profile preamble
        targets = repo.match(AlwaysTrue, sorter=sorted)

        if not targets:
            # just open/trunc the target instead, and bail
            open(self._location, 'wb')
            return



class PackagesCacheV1(PackagesCacheV0):

    inheritable = PackagesCacheV0.inheritable.union(('SLOT', 'EAPI', 'LICENSE',
        'KEYWORDS'))

    @classmethod
    def _assemble_pkg_dict(cls, pkg):
        # not the most efficient...
        d = PackagesCacheV0._assemble_pkg_dict(pkg)
        use = set(pkg.use).intersection(x.lstrip("+-") for x in pkg.iuse)
        d.pop("IUSE", None)
        iuse_bits = [x.lstrip("+-") for x in pkg.iuse]
        iuse_bits = ['-%s' % (x,) for x in iuse_bits if x not in use]
        use.update(iuse_bits)
        d["USE"] = ' '.join(sorted(use))
        return d

    version = 1


def write_index(filepath, repo, version=-1):
    if version == -1:
        version = 1
    try:
        cls = globals()['PackagesCacheV%i' % version]
    except KeyError:
        raise ValueError("unknown version")
    return cls.write_repo(filepath, repo)
