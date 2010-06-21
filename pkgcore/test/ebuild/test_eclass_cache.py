# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import os

from pkgcore.test import TestCase
from snakeoil.test.mixins import TempDirMixin
from snakeoil.osutils import pjoin
from pkgcore.ebuild import eclass_cache
from snakeoil import data_source

class FakeEclassCache(eclass_cache.base):

    def __init__(self, path):
        eclass_cache.base.__init__(self, portdir=path, eclassdir=path)
        self.eclasses = {
            "eclass1":(path, 100),
            "eclass2":(path, 200)}


class TestBase(TestCase):

    def setUp(self):
        self.dir = '/nonexistant/path/'
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
        self.assertFalse(self.ec.is_eclass_data_valid(
            {"eclass1":(self.dir, 200)}))
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


class TestEclassCache(TempDirMixin, TestBase):

    def setUp(self):
        TempDirMixin.setUp(self)
        for x, mtime in (("eclass1", 100), ("eclass2", 200)):
            open(pjoin(self.dir, "%s.eclass" % x), "w")
            os.utime(pjoin(self.dir, "%s.eclass" % x), (mtime, mtime))
        # insert a crap file to ensure it doesn't grab it.
        open(pjoin(self.dir, 'foon-eclass'), 'w')
        self.ec = eclass_cache.cache(self.dir)
        self.ec_locs = dict((x, self.dir) for x in ("eclass1", "eclass2"))

    def test_get_eclass(self):
        for x in ("eclass1", "eclass2"):
            handle = self.ec.get_eclass(x)
            self.assertInstance(handle, data_source.local_source)
            self.assertEqual(pjoin(self.ec_locs[x], "%s.eclass" % x),
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
        open(pjoin(self.loc1, 'eclass1.eclass'), 'w')
        os.utime(pjoin(self.loc1, 'eclass1.eclass'), (100, 100))
        self.ec1 = eclass_cache.cache(self.loc1)

        os.mkdir(self.loc2)
        open(pjoin(self.loc2, 'eclass2.eclass'), 'w')
        os.utime(pjoin(self.loc2, 'eclass2.eclass'), (100, 100))
        self.ec2 = eclass_cache.cache(self.loc2)
        self.ec = eclass_cache.StackedCaches([self.ec1, self.ec2])
        self.ec_locs = {"eclass1":self.loc1, "eclass2":self.loc2}
        # make a shadowed file to verify it's not seen
        open(pjoin(self.loc2, 'eclass1.eclass'), 'w')
