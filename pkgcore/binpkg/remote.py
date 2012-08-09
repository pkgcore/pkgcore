# Copyright: 2008-2010 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
remote binpkg support

Currently this primarily just holds the Packages cache used for remote, and local
binpkg repositories
"""

__all__ = ("PackagesCacheV0", "PackagesCacheV1", "write_index")


from snakeoil.mappings import ImmutableDict, StackedDict
from pkgcore import cache
from snakeoil.weakrefs import WeakRefFinalizer
from itertools import izip
import os
from snakeoil.demandload import demandload
demandload(globals(), 'errno',
    'snakeoil.chksum:get_chksums',
    'snakeoil.fileutils:AtomicWriteFile',
    'snakeoil.containers:RefCountingSet',
    'snakeoil.fileutils:readlines',
    'operator:itemgetter',
    'pkgcore:log',
    'pkgcore.restrictions.packages:AlwaysTrue',
    'time:time',
)


def _iter_till_empty_newline(data):
    for x in data:
        if not x:
            return
        k, v = x.split(':', 1)
        yield k, v.strip()


class CacheEntry(StackedDict):

    """
    customized version of StackedDict blocking pop from modifying the target

    Note that this pop doesn't through KeyError if something is missing- just
    returns None instead.  This is likely to be changed.
    """
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


cache_meta = WeakRefFinalizer
if type != cache.bulk.__metaclass__:
    class cache_meta(WeakRefFinalizer, cache.bulk.__metaclass__):
        pass


class PackagesCacheV0(cache.bulk):
    """
    Cache backend for writting binpkg Packages caches

    Note this follows version 0 semantics- not the most efficient, and
    doesn't bundle  certain useful keys like RESTRICt
    """

    __metaclass__ = cache_meta

    _header_mangling_map = ImmutableDict({
        'FEATURES':'UPSTREAM_FEATURES',
        'ACCEPT_KEYWORDS':'KEYWORDS'})

    # this maps from literal keys in the cache to .data[key] expected forms
    _deserialize_map = {'DESC':'DESCRIPTION', 'MTIME':'mtime', 'repo':'REPO'}
    # this maps from .attr to data items.
    _serialize_map   = {"DEPENDS": "DEPEND", "RDEPENDS": "RDEPEND",
        "POST_RDEPENDS":"POST_RDEPEND", "DESCRIPTION":"DESC", 'mtime':'MTIME',
        "source_repository":"REPO"}
    deserialized_inheritable = frozenset(('CBUILD', 'CHOST', 'source_repository'))
    _pkg_attr_sequences = ('use', 'keywords', 'iuse')
    _deserialized_defaults = dict.fromkeys(('BUILD_TIME', 'DEPEND', 'IUSE', 'KEYWORDS',
        'LICENSE', 'PATH', 'PDEPEND', 'PROPERTIES', 'PROVIDE', 'RDEPEND',
        'USE', 'DEFINED_PHASES', 'CHOST', 'CBUILD', 'DESC', 'REPO',
        'DESCRIPTION'),
        '')
    _deserialized_defaults.update({'EAPI':'0', 'SLOT':'0'})
    _deserialized_defaults = ImmutableDict(_deserialized_defaults)

    _stored_chfs = ('size', 'sha1', 'md5', 'mtime')

    version = 0

    def __init__(self, location, *args, **kwds):
        self._location = location
        vkeys = set(self._stored_chfs)
        vkeys.update(self._deserialized_defaults)
        vkeys.add("CPV")
        vkeys.update(x.upper() for x in self._stored_chfs)
        kwds["auxdbkeys"] = vkeys
        cache.bulk.__init__(self, *args, **kwds)

    def _handle(self):
        return readlines(self._location, True, False, False)

    def read_preamble(self, handle):
        return ImmutableDict(
            (self._header_mangling_map.get(k, k), v)
            for k,v in _iter_till_empty_newline(handle))

    def _read_data(self):
        try:
            handle = self._handle()
        except EnvironmentError, e:
            if e.errno == errno.ENOENT:
                return {}
            raise
        self.preamble = self.read_preamble(handle)

        defaults = dict(self._deserialized_defaults.iteritems())
        defaults.update((k, v) for k,v in self.preamble.iteritems()
            if k in self.deserialized_inheritable)
        defaults = ImmutableDict(defaults)

        pkgs = {}
        count = 0
        vkeys = self._known_keys
        while True:
            raw_d = dict(_iter_till_empty_newline(handle))

            d = dict((k, v) for k,v in raw_d.iteritems() if k in vkeys)
            if not d:
                break
            count += 1
            cpv = d.pop("CPV", None)
            if cpv is None:
                cpv = "%s/%s" % (d.pop("CATEGORY"), d.pop("PF"))

            if 'USE' in d:
                d.setdefault('IUSE', d.get('USE', ''))
            for src, dst in self._deserialize_map.iteritems():
                if src in d:
                    d.setdefault(dst, d.pop(src))

            pkgs[cpv] = CacheEntry(d, defaults)
        assert count == int(self.preamble.get('PACKAGES', count))
        return pkgs

    @classmethod
    def _assemble_preamble_dict(cls, target_dicts):
        preamble = {'VERSION':cls.version, 'PACKAGES':len(target_dicts),
            'TIMESTAMP':str(int(time()))}
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

        for key, value in izip(cls._stored_chfs,
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
                self._serialize_to_handle(self.data.items(), handler)
                handler.close()
            except EnvironmentError, e:
                if e.errno != errno.EACCES:
                    raise
                log.logger.error("failed writing binpkg Packages cache to %r; permissions issue %s",
                   self._location, e)
        finally:
            if handler is not None:
                handler.discard()

    def _serialize_to_handle(self, data, handler):
        preamble = self._assemble_preamble_dict(data)

        convert_key = self._serialize_map.get

        for key in sorted(preamble):
            handler.write("%s: %s\n" % (convert_key(key, key), preamble[key]))
        handler.write('\n')

        spacer = ' '
        if self.version != 0:
            spacer = ''

        vkeys = self._known_keys
        for cpv, pkg_data in sorted(data, key=itemgetter(0)):
            handler.write("CPV:%s%s\n" % (spacer, cpv))
            data = [(convert_key(key, key), value)
                for key, value in pkg_data.iteritems()]
            for write_key, value in sorted(data):
                if write_key not in vkeys:
                    continue
                value = str(value).strip()
                if write_key in preamble:
                    if value != preamble[write_key]:
                        if value:
                            handler.write("%s:%s%s\n" % (write_key, spacer, value))
                        else:
                            handler.write("%s:\n" % (write_key,))
                elif value:
                    handler.write("%s:%s%s\n" % (write_key, spacer, value))
            handler.write('\n')

    def update_from_xpak(self, pkg, xpak):
        # invert the lookups here; if you do .iteritems() on an xpak,
        # it'll load up the contents in full.
        new_dict = dict((k, xpak[k]) for k in
            self._known_keys if k in xpak)
        new_dict['_chf_'] = xpak._chf_
        chfs = [x for x in self._stored_chfs if x != 'mtime']
        for key, value in izip(chfs, get_chksums(pkg.path, *chfs)):
            if key != 'size':
                value = "%x" % (value,)
            new_dict[key.upper()] = value
        self[pkg.cpvstr] = new_dict
        return new_dict

    def update_from_repo(self, repo):
        # try to collapse certain keys down to the profile preamble
        targets = repo.match(AlwaysTrue, sorter=sorted)

        if not targets:
            # just open/trunc the target instead, and bail
            open(self._location, 'wb')
            return

    def __del__(self):
        self.commit()



class PackagesCacheV1(PackagesCacheV0):

    """
    Cache backend for writting binpkg Packages caches in format version 1

    See :py:class:`PackagesCacheV0` for usage information; this just writes
    a better ondisk format
    """

    deserialized_inheritable = PackagesCacheV0.deserialized_inheritable.union(
        ('SLOT', 'EAPI', 'LICENSE', 'KEYWORDS', 'USE', 'RESTRICT'))

    _deserialized_defaults = ImmutableDict(
        PackagesCacheV0._deserialized_defaults.items() + [('RESTRICT', '')])

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


def get_cache_kls(version):
    version = str(version)
    if version == '0':
        return PackagesCacheV0
    elif version in ('1', '-1'):
        return PackagesCacheV1
    raise KeyError("cache version %s unsupported" % (version,))


def write_index(filepath, repo, version=-1):
    """
    given a repository, serialize it's packages contents to a PackagesCache backend.

    :param filepath: path to write the cache to
    :param repo: Repository instance to serialize
    :param version: if set, this is the format version to use.  Defaults to the
        most recent (currently v1)
    """
    if version == -1:
        version = 1
    try:
        cls = globals()['PackagesCacheV%i' % version]
    except KeyError:
        raise ValueError("unknown version")
    return cls.write_repo(filepath, repo)
