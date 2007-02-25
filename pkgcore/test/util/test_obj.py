# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2


import operator
from random import random

from pkgcore.test import TestCase
from pkgcore.util import obj

# sorry, but the name is good, just too long for these tests
make_DI = obj.DelayedInstantiation
make_DIkls = obj.DelayedInstantiation_kls

class TestDelayedInstantiation(TestCase):

    def test_simple(self):
        t = (1, 2, 3)
        o = make_DI(tuple, lambda:t)
        objs = [o, t]
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
        
        # test pass through; __doc__ is useful anyways, and 
        # always available on tuple due to it being a builtin
        self.assertIdentical(t.__doc__, o.__doc__)

    def test_nonspecial(self):
        class foo(object):
            pass
        f = make_DI(foo, lambda:None)
        # it lies about it's class.  thus bypass it's web of lies...
        self.assertIdentical(object.__getattribute__(f, '__class__'),
            obj.BaseDelayedObject)

    def test_DelayedInstantiation_kls(self):
        t = (1, 2, 3)
        self.assertEqual(make_DIkls(tuple, [1,2,3]), t)

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
        # note, this *must* be isinstance, not assertInstance.
        # assertInstance triggers a repr on it, thus triggering expansion.
        # we're specifically testing that it doesn't instantiate just for
        # class.
        self.assertTrue(isinstance(o, bool))
        self.assertFalse(l)


class SlottedDictTest(TestCase):

    kls = staticmethod(obj.make_SlottedDict_kls)

    def test_reuse(self):
        # intentionally randomizing this a bit.
        a_ord = ord('a')
        z_ord = ord('z')
        l = []
        for x in xrange(10):
            s = ''
            for c in xrange(10):
                s += chr(a_ord + int(random() * (z_ord - a_ord)))
            l.append(s)
        d = self.kls(l)
        self.assertEqual(tuple(sorted(l)), d.__slots__)
        # check sorting.
        d2 = self.kls(reversed(l))
        self.assertIdentical(d, d2)

    def test_dict_basics(self):
        d = self.kls(['spork'])()
        for op in (operator.getitem, operator.delitem):
            self.assertRaises(KeyError, op, d, 'spork')
            self.assertRaises(KeyError, op, d, 'foon')

        d = self.kls(['spork', 'foon'])((('spork', 1),))
        self.assertLen(d, 1)
        self.assertEqual(d.get('spork'), 1)
        self.assertIn('spork', d)
        del d['spork']
        self.assertEqual(d.get('spork'), None)
        self.assertEqual(d.get('spork', 3), 3)

        d['spork'] = 2
        self.assertLen(d, 1)
        self.assertEqual(d.get('spork'), 2)
        self.assertEqual(d.pop('spork'), 2)
        self.assertRaises(KeyError, d.pop, 'spork')
        # check pop complains about too many args.
        self.assertRaises(TypeError, d.pop, 'spork', 'foon', 'dar')
        self.assertEqual(d.pop('spork', 2), 2)
        
        self.assertLen(d, 0)
        self.assertRaises(KeyError, d.__getitem__, 'spork')
        self.assertLen(d, 0)
        self.assertNotIn('spork', d)
        d['foon'] = 2
        self.assertIn('foon', d)
        d['spork'] = 1
        self.assertIn('spork', d)
        self.assertLen(d, 2)
        self.assertEqual(sorted(d), ['foon', 'spork'])
        self.assertEqual(sorted(d.itervalues()), [1,2])
        self.assertEqual(sorted(d.iterkeys()), ['foon', 'spork'])
        self.assertEqual(sorted(d.keys()), sorted(d.iterkeys()),
            reflective=False)
        self.assertEqual(sorted(d.values()), sorted(d.itervalues()),
            reflective=False)
        d.clear()
        self.assertLen(d, 0)
        
