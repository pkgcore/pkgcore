# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# Copyright: 2005-2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

import operator

from pkgcore.test import TestCase
from pkgcore.util import mappings, currying
from itertools import chain


def a_dozen():
    return range(12)


class RememberingNegateMixin(object):

    def setUp(self):
        self.negate_calls = []
        def negate(i):
            self.negate_calls.append(i)
            return -i
        self.negate = negate

    def tearDown(self):
        del self.negate
        del self.negate_calls


class TestDictMixin(TestCase):

    kls = mappings.DictMixin
    class ro_dict(kls):
        __getitem__ = lambda s, k:s.__dict__[k]
        iterkeys = lambda s:s.__dict__.iterkeys()

    class wr_dict(ro_dict):
        __setitem__ = lambda s, k, v: s.__dict__.__setitem__(k, v)
        __delitem__ = lambda s, k: s.__dict__.__delitem__(k)

    class test_dict(ro_dict):
        def __init__(self, initial=[]):
            self.__dict__.update(initial)

    def test_init(self):
        # shouldn't write any keys.
        self.kls()
        self.assertRaises(NotImplementedError, self.ro_dict, ((1,2), (3,4)))
        self.assertEqual(self.wr_dict(((1,2), (3,4))).__dict__,
            {1:2, 3:4})
        self.assertEqual(self.wr_dict({1:2, 3:4}.iteritems()).__dict__,
            {1:2, 3:4})

    def test_iter(self, method='__iter__', values=range(100)):
        d = self.test_dict({}.fromkeys(xrange(100)).iteritems())
        i = getattr(d, method)()
        if 'iter' not in method:
            self.assertInstance(i, (list, tuple))
        self.assertEqual(list(i), list(values))

    test_iterkeys = currying.post_curry(test_iter, method='iterkeys')
    test_iterkeys = currying.post_curry(test_iter, method='keys')

    test_itervalues = currying.post_curry(test_iter, method='itervalues',
        values=[None]*100)

    test_values = currying.post_curry(test_iter, method='values',
        values=[None]*100)

    test_iteritems = currying.post_curry(test_iter, method='iteritems',
        values={}.fromkeys(xrange(100)).items())

    test_items = currying.post_curry(test_iter, method='items',
        values={}.fromkeys(xrange(100)).items())

    def test_update(self):
        d = self.wr_dict({}.fromkeys(xrange(100)).iteritems())
        self.assertEqual(list(d.iteritems()), [(x, None) for x in xrange(100)])
        d.update((x, x) for x in xrange(100))
        self.assertEqual(list(d.iteritems()), [(x, x) for x in xrange(100)])
    
    def test_get(self):
        d = self.wr_dict([(1,2)])
        self.assertEqual(d.get(1), 2)
        self.assertEqual(d.get(1, None), 2)
        self.assertEqual(d.get(2), None)
        self.assertEqual(d.get(2, 3), 3)

    def test_contains(self):
        # ensure the default 'in' op is a key pull.
        l, state = [], False
        class tracker_dict(self.wr_dict):
            def __getitem__(self, key):
                l.append(key)
                if state:
                    return True
                raise KeyError

        d = tracker_dict()
        self.assertNotIn(1, d)
        self.assertFalse(d.has_key(1))
        self.assertEqual(l, [1, 1])
        state = True
        l[:] = []
        self.assertIn(2, d)
        self.assertTrue(d.has_key(3))
        self.assertEqual(l, [2, 3])

    def test_cmp(self):
        self.assertEqual(self.test_dict(), self.test_dict())
        d1 = self.wr_dict({})
        d2 = self.test_dict({1:2}.iteritems())
        self.assertTrue(d1 < d2)
        self.assertNotEqual(d1, d2)
        d1[1] = 2
        self.assertEqual(d1, d2)
        d1[1] = 3
        self.assertNotEqual(d1, d2)
        del d1[1]
        d1[0] = 2
        self.assertNotEqual(d1, d2)

    def test_pop(self):
        class c(self.ro_dict): __externally_mutable__ = False
        self.assertRaises(AttributeError, c().pop, 1)
        d = self.wr_dict()
        self.assertRaises(KeyError, d.pop, 1)
        self.assertEqual(d.pop(1, 2), 2)
        d[1] = 2
        # ensure it gets pissy about too many args.
        self.assertRaises(TypeError, d.pop, 1, 2, 3)
        self.assertEqual(len(d), 1)
        self.assertEqual(d.pop(1), 2)
        self.assertEqual(len(d), 0)
    
    def test_popitem(self):
        # hate this method.
        d = self.wr_dict()
        self.assertRaises(KeyError, d.popitem)
        self.assertRaises(TypeError, d.popitem, 1)
        d.update(((0,1), (1,2), (2,3)))
        self.assertLen(d, 3)
        got = d.popitem()
        self.assertNotIn(got[0], d)
        self.assertEqual(got[1], got[0] + 1)
        self.assertLen(d, 2)
        self.assertEqual(d, dict((x, x + 1) for x in xrange(3) if x != got[0]))

    def test_setdefault(self):
        d = self.wr_dict()
        self.assertEqual(d.setdefault(1, 2), 2)
        self.assertEqual(d.setdefault(1, 3), 2)

    def test_clear(self):
        d = self.wr_dict({}.fromkeys(xrange(100)).iteritems())
        self.assertEqual(d, {}.fromkeys(xrange(100)))
        self.assertEqual(d.clear(), None)
        self.assertEqual(d, {})
        d[1] = 2
        self.assertEqual(d, {1:2})

    def test_len(self):
        self.assertLen(self.ro_dict(), 0)
        d = self.wr_dict({}.fromkeys(xrange(100)).iteritems())
        self.assertLen(d, 100)
        del d[99]
        self.assertLen(d, 99)


class LazyValDictTestMixin(object):

    def test_invalid_operations(self):
        self.assertRaises(AttributeError, operator.setitem, self.dict, 7, 7)
        self.assertRaises(AttributeError, operator.delitem, self.dict, 7)

    def test_contains(self):
        self.failUnless(7 in self.dict)
        self.failIf(12 in self.dict)

    def test_keys(self):
        # Called twice because the first call will trigger a keyfunc call.
        self.failUnlessEqual(sorted(self.dict.keys()), list(xrange(12)))
        self.failUnlessEqual(sorted(self.dict.keys()), list(xrange(12)))

    def test_iterkeys(self):
        # Called twice because the first call will trigger a keyfunc call.
        self.failUnlessEqual(sorted(self.dict.iterkeys()), list(xrange(12)))
        self.failUnlessEqual(sorted(self.dict.iterkeys()), list(xrange(12)))

    def test_iteritems(self):
        i = iter(xrange(12))
        for idx, kv in enumerate(self.dict.iteritems()):
            self.assertEqual(kv, (idx, -idx))

    def test_len(self):
        # Called twice because the first call will trigger a keyfunc call.
        self.assertEqual(12, len(self.dict))
        self.assertEqual(12, len(self.dict))

    def test_getkey(self):
        self.assertEqual(self.dict[3], -3)
        # missing key
        def get():
            return self.dict[42]
        self.assertRaises(KeyError, get)

    def test_caching(self):
        # "Statement seems to have no effect"
        # pylint: disable-msg=W0104
        self.dict[11]
        self.dict[11]
        self.assertEqual(self.negate_calls, [11])


class LazyValDictWithListTest(
    TestCase, LazyValDictTestMixin, RememberingNegateMixin):

    def setUp(self):
        RememberingNegateMixin.setUp(self)
        self.dict = mappings.LazyValDict(range(12), self.negate)

    def tearDown(self):
        RememberingNegateMixin.tearDown(self)

    def test_itervalues(self):
        self.assertEqual(sorted(self.dict.itervalues()), range(-11, 1))

    def test_len(self):
        self.assertEqual(len(self.dict), 12)

    def test_iter(self):
        self.assertEqual(list(self.dict), range(12))

    def test_contains(self):
        self.assertIn(1, self.dict)

    def test_has_key(self):
        self.assertEqual(True, self.dict.has_key(1))

class LazyValDictWithFuncTest(
    TestCase, LazyValDictTestMixin, RememberingNegateMixin):

    def setUp(self):
        RememberingNegateMixin.setUp(self)
        self.dict = mappings.LazyValDict(a_dozen, self.negate)

    def tearDown(self):
        RememberingNegateMixin.tearDown(self)


class LazyValDictTest(TestCase):

    def test_invalid_init_args(self):
        self.assertRaises(TypeError, mappings.LazyValDict, [1], 42)
        self.assertRaises(TypeError, mappings.LazyValDict, 42, a_dozen)


# TODO check for valid values for dict.new, since that seems to be
# part of the interface?
class ProtectedDictTest(TestCase):

    def setUp(self):
        self.orig = {1: -1, 2: -2}
        self.dict = mappings.ProtectedDict(self.orig)

    def test_basic_operations(self):
        self.assertEqual(self.dict[1], -1)
        def get(i):
            return self.dict[i]
        self.assertRaises(KeyError, get, 3)
        self.assertEqual(sorted(self.dict.keys()), [1, 2])
        self.failIf(-1 in self.dict)
        self.failUnless(2 in self.dict)
        def remove(i):
            del self.dict[i]
        self.assertRaises(KeyError, remove, 50)

    def test_basic_mutating(self):
        # add something
        self.dict[7] = -7
        def check_after_adding():
            self.assertEqual(self.dict[7], -7)
            self.failUnless(7 in self.dict)
            self.assertEqual(sorted(self.dict.keys()), [1, 2, 7])
        check_after_adding()
        # remove it again
        del self.dict[7]
        self.failIf(7 in self.dict)
        def get(i):
            return self.dict[i]
        self.assertRaises(KeyError, get, 7)
        self.assertEqual(sorted(self.dict.keys()), [1, 2])
        # add it back
        self.dict[7] = -7
        check_after_adding()
        # remove something not previously added
        del self.dict[1]
        self.failIf(1 in self.dict)
        self.assertRaises(KeyError, get, 1)
        self.assertEqual(sorted(self.dict.keys()), [2, 7])
        # and add it back
        self.dict[1] = -1
        check_after_adding()
        # Change an existing value, then remove it:
        self.dict[1] = 33
        del self.dict[1]
        self.assertNotIn(1, self.dict)


class ImmutableDictTest(TestCase):

    def setUp(self):
        self.dict = mappings.ImmutableDict(**{1: -1, 2: -2})

    def test_invalid_operations(self):
        initial_hash = hash(self.dict)
        self.assertRaises(TypeError, operator.delitem, self.dict, 1)
        self.assertRaises(TypeError, operator.delitem, self.dict, 7)
        self.assertRaises(TypeError, operator.setitem, self.dict, 1, -1)
        self.assertRaises(TypeError, operator.setitem, self.dict, 7, -7)
        self.assertRaises(TypeError, self.dict.clear)
        self.assertRaises(TypeError, self.dict.update, {6: -6})
        self.assertRaises(TypeError, self.dict.pop, 1)
        self.assertRaises(TypeError, self.dict.popitem)
        self.assertRaises(TypeError, self.dict.setdefault, 6, -6)
        self.assertEqual(initial_hash, hash(self.dict))


class StackedDictTest(TestCase):

    orig_dict = dict.fromkeys(xrange(100))
    new_dict = dict.fromkeys(xrange(100, 200))

    def test_contains(self):
        std	= mappings.StackedDict(self.orig_dict, self.new_dict)
        self.failUnless(1 in std)
        self.failUnless(std.has_key(1))

    def test_stacking(self):
        o = dict(self.orig_dict)
        std = mappings.StackedDict(o, self.new_dict)
        for x in chain(*map(iter, (self.orig_dict, self.new_dict))):
            self.failUnless(x in std)

        map(o.__delitem__, iter(self.orig_dict))
        for x in self.orig_dict:
            self.failIf(x in std)
        for x in self.new_dict:
            self.failUnless(x in std)

    def test_len(self):
        self.assertEqual(sum(map(len, (self.orig_dict, self.new_dict))),
            len(mappings.StackedDict(self.orig_dict, self.new_dict)))

    def test_setattr(self):
        self.assertRaises(TypeError, mappings.StackedDict().__setitem__, (1, 2))

    def test_delattr(self):
        self.assertRaises(TypeError, mappings.StackedDict().__delitem__, (1, 2))

    def test_clear(self):
        self.assertRaises(TypeError, mappings.StackedDict().clear)

    def test_iter(self):
        s = set()
        map(s.add, chain(iter(self.orig_dict), iter(self.new_dict)))
        for x in mappings.StackedDict(self.orig_dict, self.new_dict):
            self.failUnless(x in s)
            s.remove(x)
        self.assertEqual(len(s), 0)

    def test_keys(self):
        self.assertEqual(
            sorted(mappings.StackedDict(self.orig_dict, self.new_dict)),
            sorted(self.orig_dict.keys() + self.new_dict.keys()))

    def test_getitem(self):
        o = mappings.StackedDict({1:1}, {1:1, 2:2}, {1:3, 3:3})
        self.assertEqual(o[1], 1)
        self.assertEqual(o[2], 2)
        self.assertEqual(o[3], 3)
        self.assertRaises(KeyError, o.__getitem__, 4)


class IndeterminantDictTest(TestCase):

    def test_disabled_methods(self):
        d = mappings.IndeterminantDict(lambda *a: None)
        for x in ("clear", ("update", {}), ("setdefault", 1),
            "__iter__", "__len__", "__hash__", ("__delitem__", 1),
            ("__setitem__", 2), ("popitem", 2), "iteritems", "iterkeys",
            "keys", "items", "itervalues", "values"):
            if isinstance(x, tuple):
                self.assertRaises(TypeError, getattr(d, x[0]), x[1])
            else:
                self.assertRaises(TypeError, getattr(d, x))

    def test_starter_dict(self):
        d = mappings.IndeterminantDict(
            lambda key: False, starter_dict={}.fromkeys(xrange(100), True))
        for x in xrange(100):
            self.assertEqual(d[x], True)
        for x in xrange(100, 110):
            self.assertEqual(d[x], False)

    def test_behaviour(self):
        val = []
        d = mappings.IndeterminantDict(
            lambda key: val.append(key), {}.fromkeys(xrange(10), True))
        self.assertEqual(d[0], True)
        self.assertEqual(d[11], None)
        self.assertEqual(val, [11])
        def func(*a):
            raise KeyError
        self.assertRaises(
            KeyError, mappings.IndeterminantDict(func).__getitem__, 1)
        self.assertEqual(mappings.IndeterminantDict(func).pop(100, 1), 1)
        self.assertEqual(mappings.IndeterminantDict(func).pop(100), None)
        
        d.pop(1)
        self.assertEqual(d[1], True)

    def test_get(self):
        def func(key):
            if key == 2:
                raise KeyError
            return True
        d = mappings.IndeterminantDict(func, {1:1})
        self.assertEqual(d.get(1, 1), 1)
        self.assertEqual(d.get(1, 2), 1)
        self.assertEqual(d.get(2), None)
        self.assertEqual(d.get(2, 2), 2)
        self.assertEqual(d.get(3), True)


class TestOrderedDict(TestCase):

    @staticmethod
    def gen_dict():
        return mappings.OrderedDict(enumerate(xrange(100)))

    def test_items(self):
        self.assertEqual(list(self.gen_dict().iteritems()),
            list(enumerate(xrange(100))))
        self.assertEqual(self.gen_dict().items(),
            list(enumerate(xrange(100))))

    def test_values(self):
        self.assertEqual(list(self.gen_dict().itervalues()),
            list(xrange(100)))
        l = ["asdf", "fdsa", "Dawefa", "3419", "pas", "1"]
        l = [s+"12" for s in l] + l
        l = ["1231adsfasdfagqwer"+s for s in l] + l
        self.assertEqual(
            list(mappings.OrderedDict(
                    (v, k) for k, v in enumerate(l)).itervalues()),
            list(xrange(len(l))))

    def test_keys(self):
        self.assertEqual(list(self.gen_dict().iterkeys()), list(xrange(100)))
        self.assertEqual(self.gen_dict().keys(), list(xrange(100)))

    def test_iter(self):
        self.assertEqual(list(self.gen_dict()), list(xrange(100)))
        l = ["asdf", "fdsa", "Dawefa", "3419", "pas", "1"]
        l = [s+"12" for s in l] + l
        l = ["1231adsfasdfagqwer"+s for s in l] + l
        self.assertEqual(list(mappings.OrderedDict((x, None) for x in l)), l)

    def test_del(self):
        d = self.gen_dict()
        del d[50]
        self.assertEqual(list(d), list(range(50) + range(51, 100)))
        self.assertRaises(KeyError, operator.delitem, d, 50)
        self.assertRaises(KeyError, operator.delitem, d, 'spork')

    def test_set(self):
        d = self.gen_dict()
        d.setdefault(120)
        d.setdefault(110)
        self.assertEqual(list(d), list(range(100)) + [120, 110])

    def test_clear(self):
        self.gen_dict().clear()
