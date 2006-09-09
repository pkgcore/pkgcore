# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.util.weakrefs import WeakValCache
from weakref import WeakValueDictionary

class RefObj(object):
    pass

class TestWeakValCache(unittest.TestCase):
    if WeakValueDictionary is WeakValCache:
        skip = "WeakValCache is weakref.WeakValueDictionary; indicates " \
            "pkgcore.util._caching isn't compiled"
    
    def setUp(self):
        self.o = RefObj()
        self.w = WeakValCache()
    
    def test_setitem(self):
        s = "asdf"
        self.w[s] = self.o
        self.w["fds"] = self.o
        self.w[s] = self.o
    
    def test_getitem(self):
        s = "asdf"
        self.w[s] = self.o
        self.assertIdentical(self.w[s], self.o)

    def test_expiring(self):
        s = "asdf"
        self.w[s] = self.o
        self.assertTrue(self.w[s])
        del self.o
        self.assertRaises(KeyError, self.w.__getitem__, s)

    def test_get(self):
        s = "asdf"
        self.assertRaises(KeyError, self.w.__getitem__, s)
        self.w[s] = self.o
        self.assertIdentical(self.w.get(s), self.o)
