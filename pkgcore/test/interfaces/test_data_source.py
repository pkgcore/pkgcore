# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os
from snakeoil.test import TestCase
from pkgcore.interfaces import data_source
from pkgcore.test.mixins import TempDirMixin


class TestDataSource(TestCase):

    def get_obj(self, mutable=False):
        return data_source.data_source("foonani", mutable=mutable)

    def test_get_path(self):
        obj = self.get_obj()
        self.assertIdentical(obj.get_path, None)

    def test_get_fileobj(self):
        obj = self.get_obj()
        self.assertEqual(obj.get_fileobj().read(), "foonani")

        obj = self.get_obj(True)
        self.assertEqual(obj.get_fileobj().read(), "foonani")
        f = obj.get_fileobj()
        f.write("dar")
        f.close()
        self.assertEqual(obj.get_fileobj().read(), "darnani")


class TestLocalSource(TempDirMixin, TestDataSource):

    def get_obj(self, mutable=False):
        self.fp = os.path.join(self.dir, "localsource.test")
        open(self.fp, "w").write("foonani")
        return data_source.local_source(self.fp, mutable=mutable)

    def test_get_path(self):
        self.assertEqual(self.get_obj().get_path(), self.fp)

