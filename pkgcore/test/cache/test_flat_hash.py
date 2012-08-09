# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.test.cache import util, test_base
from pkgcore.cache import flat_hash
from snakeoil.test.mixins import TempDirMixin


class db(flat_hash.database):

    def __setitem__(self, cpv, data):
        data['_chf_'] = test_base._chf_obj
        return flat_hash.database.__setitem__(self, cpv, data)

    def __getitem__(self, cpv):
        d = dict(flat_hash.database.__getitem__(self, cpv).iteritems())
        d.pop('_%s_' % self.chf_type, None)
        return d


class TestFlatHash(util.GenericCacheMixin, TempDirMixin):

    def get_db(self, readonly=False):
        return db(self.dir,
            auxdbkeys=self.cache_keys, readonly=readonly)
