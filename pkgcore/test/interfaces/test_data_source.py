# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import os
from pkgcore.test import TestCase
from pkgcore.interfaces import data_source
from snakeoil.test.mixins import TempDirMixin
from snakeoil import compatibility


class TestDataSource(TestCase):

    def get_obj(self, mutable=False):
        return data_source.data_source("foonani", mutable=mutable)

    def test_get_path(self):
        obj = self.get_obj()
        self.assertIdentical(obj.get_path, None)

    def test_get_text_fileobj(self):
        obj = self.get_obj()
        self.assertEqual(obj.get_text_fileobj().read(), "foonani")
        val = getattr(obj.get_text_fileobj(), 'write', None)
        self.assertRaises(TypeError, obj.get_text_fileobj, True)
        if val is not None:
            self.assertRaises((IOError, AttributeError), val, 'dar')

        obj = self.get_obj(True)
        self.assertEqual(obj.get_text_fileobj().read(), "foonani")
        f = obj.get_text_fileobj(True)
        f.write("dar")
        f.close()
        self.assertEqual(obj.get_text_fileobj().read(), "darnani")

    def test_get_bytes_fileobj(self):
        obj = self.get_obj()
        self.assertRaises(TypeError, obj.get_bytes_fileobj, True)
        obj = self.get_obj(True)
        self.assertTrue(obj.get_bytes_fileobj())


class TestLocalSource(TempDirMixin, TestDataSource):

    def get_obj(self, mutable=False, data="foonani"):
        self.fp = os.path.join(self.dir, "localsource.test")
        f = None
        if compatibility.is_py3k:
            if isinstance(data, bytes):
                f = open(self.fp, 'wb')
        if f is None:
            f = open(self.fp, "w")
        f.write(data)
        return data_source.local_source(self.fp, mutable=mutable)

    def test_get_path(self):
        self.assertEqual(self.get_obj().get_path(), self.fp)

    def test_get_bytes_fileobj(self):
        data = u"foonani\xf2".encode("utf8")
        obj = self.get_obj(data=data)
        # this will blow up if tries to ascii decode it.
        self.assertEqual(obj.get_bytes_fileobj().read(), data)
