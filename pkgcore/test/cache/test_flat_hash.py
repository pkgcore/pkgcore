# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test.cache import util
from pkgcore.cache import flat_hash
from pkgcore.test.mixins import TempDirMixin

class TestFlatHash(util.GenericCacheMixin, TempDirMixin):

    def get_db(self, readonly=False):
        return flat_hash.database(self.dir, "test",
            self.cache_keys, readonly=readonly)
