# Copyright: 2008-2009 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from snakeoil.mappings import ImmutableDict, StackedDict
from snakeoil import klass
from pkgcore.ebuild.cpv import versioned_CPV
from pkgcore.chksum import get_handlers

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


class PackagesCache(object):

    _header_mangling_map = ImmutableDict({'USE':'UPSTREAM_USE',
        'FEATURES':'UPSTREAM_FEATURES',
        'ACCEPT_KEYWORDS':'KEYWORDS'})

    _rewrite_map = {'DESC':'DESCRIPTION'}

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
