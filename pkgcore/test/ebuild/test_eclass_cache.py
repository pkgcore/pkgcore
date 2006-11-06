# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2


from pkgcore.ebuild import eclass_cache
from pkgcore.interfaces import data_source
import os

from pkgcore.test.mixins import TempDirMixin
from pkgcore.test import TestCase

class FakeEclassCache(eclass_cache.base):

    def __init__(self, path):
        eclass_cache.base.__init__(self, portdir=path, eclassdir=path)
        self.eclasses = {
            "eclass1":(path, 100),
            "eclass2":(path, 200)}


class TestBase(TempDirMixin, TestCase):

    def setUp(self):
        TempDirMixin.setUp(self)
        self.ec = FakeEclassCache(self.dir)
        self.ec_locs = dict((x, self.dir) for x in ("eclass1", "eclass2"))
 
    def test_is_eclass_data_valid(self):
        self.assertFalse(self.ec.is_eclass_data_valid(
            {"eclass3":("foon", 100)}))
        self.assertTrue(self.ec.is_eclass_data_valid(
            {"eclass1":("", 100)}))
        self.assertFalse(self.ec.is_eclass_data_valid(
            {"eclass3":(self.dir, 100)}))
        self.assertTrue(self.ec.is_eclass_data_valid(
            {"eclass1":(self.dir, 100)}))
        self.assertTrue(self.ec.is_eclass_data_valid(
            {"eclass1":(self.ec_locs["eclass1"], 100)}))

    def test_get_eclass_data(self):
        keys = self.ec.eclasses.keys()
        data = self.ec.get_eclass_data([])
        self.assertIdentical(data, self.ec.get_eclass_data([]))
        data = self.ec.get_eclass_data(keys)
        self.assertIdentical(data, self.ec.get_eclass_data(keys))
        self.assertEqual(sorted(keys), sorted(data))
        data = self.ec.get_eclass_data(["eclass1"])
        self.assertEqual(data, {"eclass1":(self.ec_locs["eclass1"], 100)})


class TestEclassCache(TestBase):
    
    def setUp(self):
        TempDirMixin.setUp(self)
        for x, mtime in (("eclass1", 100), ("eclass2", 200)):
            open(os.path.join(self.dir, "%s.eclass" % x), "w")
            os.utime(os.path.join(self.dir, "%s.eclass" % x), (mtime, mtime))
        self.ec = eclass_cache.cache(self.dir)
        self.ec_locs = dict((x, self.dir) for x in ("eclass1", "eclass2"))

    def test_get_eclass(self):
        for x in ("eclass1", "eclass2"):
            handle = self.ec.get_eclass(x)
            self.assertTrue(isinstance(handle, data_source.local_source))
            self.assertEqual(os.path.join(self.ec_locs[x], "%s.eclass" % x),
                handle.path)
        
class TestStackedCaches(TestEclassCache):
    
    def setUp(self):
        TempDirMixin.setUp(self)
        self.loc1 = os.path.join(self.dir, "stack1")
        self.loc2 = os.path.join(self.dir, "stack2")

        os.mkdir(self.loc1)
        open(os.path.join(self.loc1, 'eclass1.eclass'), 'w')
        os.utime(os.path.join(self.loc1, 'eclass1.eclass'), (100, 100))
        self.ec1 = eclass_cache.cache(self.loc1)

        os.mkdir(self.loc2)
        open(os.path.join(self.loc2, 'eclass2.eclass'), 'w')
        os.utime(os.path.join(self.loc2, 'eclass2.eclass'), (100, 100))
        self.ec2 = eclass_cache.cache(self.loc2)
        self.ec = eclass_cache.StackedCaches([self.ec1, self.ec2])
        self.ec_locs = {"eclass1":self.loc1, "eclass2":self.loc2}
        # make a shadowed file to verify it's not seen
        open(os.path.join(self.loc2, 'eclass1.eclass'), 'w')
