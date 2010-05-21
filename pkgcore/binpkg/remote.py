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
from itertools import imap, izip
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


class PackagesCacheV0(object):

    _header_mangling_map = ImmutableDict({'USE':'UPSTREAM_USE',
        'FEATURES':'UPSTREAM_FEATURES',
        'ACCEPT_KEYWORDS':'KEYWORDS'})

    _rewrite_map = {'DESC':'DESCRIPTION'}
    _write_translate = {"DEPENDS": "DEPEND", "RDEPENDS": "RDEPEND",
        "POST_RDEPENDS":"POST_RDEPEND", "DESCRIPTION":"DESC"}
    inheritable = ('USE', 'CBUILD', 'CHOST',)
    _sequences = ('use', 'keywords', 'iuse')
    _stored_attrs = ('depends', 'rdepends', 'post_rdepends', 'use', 'keywords',
            'description', 'license', 'slot', 'cbuild', 'chost', 'eapi', 'iuse')
    _stored_chfs = ('size', 'sha1', 'md5')
    version = 0

    def __init__(self, source):
        self._source = source

    @klass.jit_attr
    def data(self):
        if isinstance(self._source, basestring):
            return iter(open(self._source))
        return iter(self._source)

    @klass.jit_attr
    def defaults(self):
        return ImmutableDict(
            (self._header_mangling_map.get(k, k), v)
            for k,v in iter_till_empty_newline(self.data))

    @klass.jit_attr
    def pkg_dict(self):
        self.defaults
        pkgs = {}
        count = 0
        while True:
            d = dict(iter_till_empty_newline(self.data))
            if not d:
                break
            count += 1
            try:
                cpv = versioned_CPV(d.pop("CPV"))
            except KeyError:
                # wanker, old format.
                cpv = versioned_CPV("%s/%s" % (d.pop("CATEGORY"), d.pop("PF")))

            d.setdefault('IUSE', d.get('USE', ''))
            for src, dst in self._rewrite_map.iteritems():
                d.setdefault(dst, d.pop(src, ''))

            pkgs.setdefault(cpv.category, {}).setdefault(cpv.package, {})[
                cpv.version] = CacheEntry(d, self.defaults)
        assert count == int(self.defaults.get('PACKAGES', count))
        return pkgs

    @classmethod
    def _assemble_preamble_dict(cls, target_dicts):
        preamble = {'VERSION':cls.version, 'PACKAGES':len(target_dicts)}
        for key in cls.inheritable:
            try:
                preamble[key] = find_best_savings(
                    (d.get(key, '') for d in target_dicts), key)
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

    @classmethod
    def write_repo(cls, target_source, repo):
        # try to collapse certain keys down to the profile preamble
        targets = repo.match(AlwaysTrue, sorter=sorted)

        if not targets:
            # just open/trunc the target instead, and bail
            open(target_source, 'wb')
            return

        handler = AtomicWriteFile(target_source)

        data = [cls._assemble_pkg_dict(pkg) for pkg in targets]
        preamble = cls._assemble_preamble_dict(data)

        for key in sorted(preamble):
            handler.write("%s: %s\n" % (key, preamble[key]))
        handler.write('\n')

        spacer = ' '
        if cls.version != 0:
            spacer = ''

        for pkg, pkg_data in izip(targets, data):
            handler.write("CPV:%s%s\n" % (pkg.cpvstr, spacer))
            for key in sorted(pkg_data):
                value = pkg_data[key]
                if key in preamble:
                    if value != preamble[key]:
                        if value:
                            handler.write("%s:%s%s\n" % (key, spacer, value))
                        else:
                            handler.write("%s:\n" % (key,))
                elif value:
                    handler.write("%s:%s%s\n" % (key, spacer, value))
            handler.write('\n')
        handler.close()
        return cls(target_source)


class PackagesCacheV1(PackagesCacheV0):

    inheritable = PackagesCacheV0.inheritable + ('SLOT', 'EAPI', 'LICENSE',
        'KEYWORDS')

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
