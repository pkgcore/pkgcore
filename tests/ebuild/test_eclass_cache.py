import os

from snakeoil import data_source
from snakeoil.chksum import LazilyHashedPath
from snakeoil.osutils import pjoin
from snakeoil.test import TestCase
from snakeoil.test.mixins import TempDirMixin

from pkgcore.ebuild import eclass_cache


class FakeEclassCache(eclass_cache.base):

    def __init__(self, path):
        eclass_cache.base.__init__(self, location=path, eclassdir=path)
        self.eclasses = {
            "eclass1":LazilyHashedPath(path, mtime=100),
            "eclass2":LazilyHashedPath(path, mtime=200)}


class TestBase(TestCase):

    def setUp(self):
        self.dir = '/nonexistent/path/'
        self.ec = FakeEclassCache(self.dir)
        self.ec_locs = {x: self.dir for x in ("eclass1", "eclass2")}

    def test_rebuild_eclass_entry(self):
        def assertRebuildResults(result, *raw_data):
            i = iter(raw_data)
            data = [(ec, [('mtime', mtime)]) for ec, mtime in zip(i, i)]
            got = self.ec.rebuild_cache_entry(data)
            self.assertTrue(bool(got) == bool(result),
                msg=f"Expected {result!r} from {raw_data!r}, got {got!r}")

        assertRebuildResults(False, 'eclass3', 100)
        assertRebuildResults(True, 'eclass1', 100)
        assertRebuildResults(False, 'eclass1', 200)

    def test_get_eclass_data(self):
        keys = list(self.ec.eclasses.keys())
        data = self.ec.get_eclass_data([])
        self.assertIdentical(data, self.ec.get_eclass_data([]))
        data = self.ec.get_eclass_data(keys)
        self.assertIdentical(data, self.ec.get_eclass_data(keys))
        self.assertEqual(sorted(keys), sorted(data))
        data = self.ec.get_eclass_data(["eclass1"])
        self.assertEqual(data, {'eclass1':self.ec.eclasses['eclass1']})


class TestEclassCache(TempDirMixin, TestBase):

    def setUp(self):
        TempDirMixin.setUp(self)
        for x, mtime in (("eclass1", 100), ("eclass2", 200)):
            open(pjoin(self.dir, f"{x}.eclass"), "w").close()
            os.utime(pjoin(self.dir, f"{x}.eclass"), (mtime, mtime))
        # insert a crap file to ensure it doesn't grab it.
        open(pjoin(self.dir, 'foon-eclass'), 'w').close()
        self.ec = eclass_cache.cache(self.dir)
        self.ec_locs = {x: self.dir for x in ("eclass1", "eclass2")}

    def test_get_eclass(self):
        for x in ("eclass1", "eclass2"):
            handle = self.ec.get_eclass(x)
            self.assertInstance(handle, data_source.local_source)
            self.assertEqual(pjoin(self.ec_locs[x], f"{x}.eclass"),
                handle.path)

        # note an eclass, thus shouldn't grab it.
        self.assertEqual(None, self.ec.get_eclass("foon"))
        self.assertEqual(None, self.ec.get_eclass("foon-eclass"))


class TestStackedCaches(TestEclassCache):

    def setUp(self):
        TempDirMixin.setUp(self)
        self.loc1 = pjoin(self.dir, "stack1")
        self.loc2 = pjoin(self.dir, "stack2")

        os.mkdir(self.loc1)
        open(pjoin(self.loc1, 'eclass1.eclass'), 'w').close()
        os.utime(pjoin(self.loc1, 'eclass1.eclass'), (100, 100))
        self.ec1 = eclass_cache.cache(self.loc1)

        os.mkdir(self.loc2)
        open(pjoin(self.loc2, 'eclass2.eclass'), 'w').close()
        os.utime(pjoin(self.loc2, 'eclass2.eclass'), (100, 100))
        self.ec2 = eclass_cache.cache(self.loc2)
        self.ec = eclass_cache.StackedCaches([self.ec1, self.ec2])
        self.ec_locs = {"eclass1":self.loc1, "eclass2":self.loc2}
        # make a shadowed file to verify it's not seen
        open(pjoin(self.loc2, 'eclass1.eclass'), 'w').close()
