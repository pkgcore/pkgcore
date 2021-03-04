from snakeoil.test.mixins import TempDirMixin

from pkgcore.cache import flat_hash

from . import test_base
from .test_util import GenericCacheMixin


class db(flat_hash.database):

    def __setitem__(self, cpv, data):
        data['_chf_'] = test_base._chf_obj
        return flat_hash.database.__setitem__(self, cpv, data)

    def __getitem__(self, cpv):
        d = dict(flat_hash.database.__getitem__(self, cpv).items())
        d.pop(f'_{self.chf_type}_', None)
        return d


class TestFlatHash(GenericCacheMixin, TempDirMixin):

    def get_db(self, readonly=False):
        return db(self.dir,
            auxdbkeys=self.cache_keys, readonly=readonly)
