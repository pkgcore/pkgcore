# Copyright: 2006-2009 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import os

from pkgcore.test import TestCase
from snakeoil.currying import partial

from snakeoil.chksum import get_handlers
from pkgcore.fetch import base, fetchable, errors
from snakeoil import data_source
from snakeoil.test.mixins import TempDirMixin

repeating_str = 'asdf'
data = repeating_str * 4000
handlers = get_handlers()

from snakeoil.mappings import LazyValDict
def _callback(chf):
    return handlers[chf](data_source.data_source(data))
chksums = LazyValDict(frozenset(handlers.iterkeys()), _callback)

# get a non size based chksum
known_chksum = [x for x in handlers.iterkeys() if x != "size"][0]

class TestFetcher(TempDirMixin, TestCase):

    def setUp(self):
        TempDirMixin.setUp(self)
        self.fp = os.path.join(self.dir, "test")
        self.obj = fetchable(self.fp, chksums=chksums)
        self.fetcher = base.fetcher()

    def write_data(self, data=data):
        open(self.fp, "w").write(data)

    def test__call__(self):
        l = []
        class c(base.fetcher):
            def fetch(self, *a, **kw):
                l.extend((a, kw))

        o = c()
        o.fetch(1, foon=True)
        self.assertEqual([(1,), {"foon":True}], l)
        class d(base.fetcher):
            __parent = self
            def get_path(self, fetchable):
                if self._verify(self.__parent.fp, fetchable) == 0:
                    return self.__parent.fp
                return None
        self.write_data()
        self.assertEqual(d().get_path(self.obj), self.fp)
        self.write_data("asdf")
        self.assertEqual(d().get_path(self.obj), None)

    def test_verify_all_chksums(self):
        self.write_data()
        subhandlers = dict([handlers.items()[0]])
        self.assertRaises(errors.RequiredChksumDataMissing,
            self.fetcher._verify, self.fp, self.obj, handlers=subhandlers)
        self.fetcher._verify(self.fp, self.obj)
        self.assertEqual(0, self.fetcher._verify(self.fp, self.obj,
            handlers=subhandlers, all_chksums=False))

    def test_size_verification_first(self):
        self.write_data()
        chksum_data = dict(chksums.iteritems())
        l = []
        def f(chf, fp):
            l.append(chf)
            return chksum_data[chf]
        subhandlers = {"size":partial(f, 'size'),
            known_chksum:partial(f, known_chksum)}

        # exact size verification
        self.fetcher._verify(self.fp, self.obj, handlers=subhandlers,
            all_chksums=False)
        self.assertEqual(['size', known_chksum], l)
        for x in (-100, 100):
            while l:
                l.pop(-1)
            chksum_data["size"] = chksums["size"] + x
            self.fetcher._verify(self.fp, self.obj, handlers=subhandlers,
                all_chksums=False)
            self.assertEqual(['size'], l)

    def test_normal(self):
        self.write_data()
        self.assertEqual(self.fetcher._verify(self.fp, self.obj), 0)
        self.write_data(data[:-1])
        self.assertEqual(self.fetcher._verify(self.fp, self.obj), -1)
        # verify it returns -2 for missing file paths.
        os.unlink(self.fp)
        self.assertEqual(self.fetcher._verify(self.fp, self.obj), -2)
        self.write_data(data + "foon")
        self.assertEqual(self.fetcher._verify(self.fp, self.obj), 1)

        # verify they're ran one, and only once
        l = []
        def f(chf, fp):
            l.append(chf)
            return chksums[chf]

        alt_handlers = dict((chf, partial(f, chf)) for chf in chksums)
        self.assertEqual(self.fetcher._verify(self.fp, self.obj,
            handlers=alt_handlers), 0)
        self.assertEqual(sorted(l), sorted(alt_handlers))
