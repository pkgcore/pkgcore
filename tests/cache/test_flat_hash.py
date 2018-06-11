# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from snakeoil.test.mixins import TempDirMixin

from pkgcore.cache import flat_hash
from tests.cache import test_base
from tests.cache.test_util import GenericCacheMixin


class db(flat_hash.database):

    def __setitem__(self, cpv, data):
        data['_chf_'] = test_base._chf_obj
        return flat_hash.database.__setitem__(self, cpv, data)

    def __getitem__(self, cpv):
        d = dict(flat_hash.database.__getitem__(self, cpv).items())
        d.pop('_%s_' % self.chf_type, None)
        return d


class TestFlatHash(GenericCacheMixin, TempDirMixin):

    def get_db(self, readonly=False):
        return db(self.dir,
            auxdbkeys=self.cache_keys, readonly=readonly)
