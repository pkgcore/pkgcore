# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase
from pkgcore.util import obj

# sorry, but the name is good, just too long for these tests
make_DI = obj.DelayedInstantiation
make_DIkls = obj.DelayedInstantiation_kls

class TestDelayedInstantiation(TestCase):

    def test_simple(self):
        t = tuple([1,2,3])
        o = make_DI(tuple, lambda:t)
        objs = [o,t]
        self.assertEqual(*map(str, objs))
        self.assertEqual(*map(repr, objs))
        self.assertEqual(*map(hash, objs))
        self.assertEqual(*objs)
        self.assertTrue(cmp(t, o) == 0)
        self.assertFalse(t < o)
        self.assertTrue(t <= o)
        self.assertTrue(t == o)
        self.assertTrue(t >= o)
        self.assertFalse(t > o)
        self.assertFalse(t != o)
        
    
    def test_descriptor_awareness(self):
        o = set(obj.kls_descriptors.difference(dir(object)))
        o.difference_update(dir(1))
        o.difference_update(dir('s'))
        o.difference_update(dir(list))
        o.difference_update(dir({}))
        
    def test_BaseDelayedObject(self):
        # assert that all methods/descriptors of object
        # are covered via the base.
        o = set(dir(object)).difference("__%s__" % x for x in
            ["class", "getattribute", "new", "init"])
        self.assertFalse(o.difference(obj.base_kls_descriptors))

    def test__class__(self):
        l = []
        def f():
            l.append(False)
            return True
        o = make_DI(bool, f)
        self.assertTrue(isinstance(o, bool))
        self.assertFalse(l)
