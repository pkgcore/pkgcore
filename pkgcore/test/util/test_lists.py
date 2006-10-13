# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from pkgcore.test import TestCase
from pkgcore.util import lists
from pkgcore.util.mappings import OrderedDict

class UnhashableComplex(complex):

    def __hash__(self):
        raise TypeError


class UniqueTest(TestCase):

    def common_check(self, func):
        # silly
        self.assertEquals(func(()), [])
        # hashable
        self.assertEquals(sorted(func([1, 1, 2, 3, 2])), [1, 2, 3])
        # neither

    def test_stable_unique(self):
        self.common_check(lists.stable_unique)

    def test_unstable_unique(self):
        self.common_check(lists.unstable_unique)
        uc = UnhashableComplex
        res = lists.unstable_unique([uc(1, 0), uc(0, 1), uc(1, 0)])
        # sortable
        self.assertEquals(sorted(lists.unstable_unique(
                    [[1, 2], [1, 3], [1, 2], [1, 3]])), [[1, 2], [1, 3]])
        self.failUnless(
            res == [uc(1, 0), uc(0, 1)] or res == [uc(0, 1), uc(1, 0)], res)


class ChainedListsTest(TestCase):

    @staticmethod
    def gen_cl():
        return lists.ChainedLists(range(3), range(3, 6), range(6, 100))

    def test_contains(self):
        cl = self.gen_cl()
        for x in (1, 2, 4, 99):
            self.assertTrue(x in cl)

    def test_iter(self):
        self.assertEquals(list(self.gen_cl()), list(xrange(100)))

    def test_len(self):
        self.assertEquals(100, len(self.gen_cl()))

    def test_getitem(self):
        cl = self.gen_cl()
        for x in (1, 2, 4, 98, -1, -99, 0):
            # "Statement seems to have no effect"
            # pylint: disable-msg=W0104
            cl[x]
        self.assertRaises(IndexError, cl.__getitem__, 100)
        self.assertRaises(IndexError, cl.__getitem__, -101)

    def test_mutable(self):
        self.assertRaises(TypeError, self.gen_cl().__delitem__, 1)
        self.assertRaises(TypeError, self.gen_cl().__setitem__, (1, 2))

    def test_append(self):
        cl = self.gen_cl()
        cl.append(range(10))
        self.assertEquals(110, len(cl))

    def test_extend(self):
        cl = self.gen_cl()
        cl.extend(range(10) for i in range(5))
        self.assertEquals(150, len(cl))


class Test_iflatten_instance(TestCase):
    func = staticmethod(lists.native_iflatten_instance)

    def test_it(self):
        o = OrderedDict((k, None) for k in xrange(10))
        for l, correct, skip in [
            (["asdf", ["asdf", "asdf"], 1, None],
            ["asdf", "asdf", "asdf", 1, None], basestring),
            ([o, 1, "fds"], [o, 1, "fds"], (basestring, OrderedDict)),
            ([o, 1, "fds"], range(10) + [1, "fds"], basestring),
            ("fds", ["fds"], basestring),
            ]:
            iterator = self.func(l, skip)
            self.assertEqual(list(iterator), correct)
            self.assertEqual([], list(iterator))
        # There is a small difference between the cpython and native
        # version: the cpython one raises immediately, for native we
        # have to iterate.
        def fail():
            return list(self.func(None))
        self.assertRaises(TypeError, fail)

        # Yes, no sane code does this, but even insane code shouldn't
        # kill the cpython version.
        iters = []
        iterator = self.func(iters)
        iters.append(iterator)
        self.assertRaises(ValueError, iterator.next)

        # Regression test: this was triggered through demandload.
        self.failUnless(self.func((), **{}))


class Test_iflatten_func(TestCase):
    func = staticmethod(lists.native_iflatten_func)

    def test_it(self):
        o = OrderedDict((k, None) for k in xrange(10))
        for l, correct, skip in [
            (["asdf", ["asdf", "asdf"], 1, None],
            ["asdf", "asdf", "asdf", 1, None], basestring),
            ([o, 1, "fds"], [o, 1, "fds"], (basestring, OrderedDict)),
            ([o, 1, "fds"], range(10) + [1, "fds"], basestring),
            ("fds", ["fds"], basestring),
            ]:
            iterator = self.func(l, lambda x:isinstance(x, skip))
            self.assertEqual(list(iterator), correct)
            self.assertEqual(list(iterator), [])
        # There is a small difference between the cpython and native
        # version: the cpython one raises immediately, for native we
        # have to iterate.
        def fail():
            return list(self.func(None, lambda x: False))
        self.assertRaises(TypeError, fail)

        # Yes, no sane code does this, but even insane code shouldn't
        # kill the cpython version.
        iters = []
        iterator = self.func(iters, lambda x: False)
        iters.append(iterator)
        self.assertRaises(ValueError, iterator.next)

        # Regression test: this was triggered through demandload.
        self.failUnless(self.func((), lambda x: True, **{}))


class CPY_Test_iflatten_instance(Test_iflatten_instance):
    func = staticmethod(lists.iflatten_instance)
    if not lists.cpy_builtin:
        skip = "cpython extension isn't available"

class CPY_Test_iflatten_func(Test_iflatten_func):
    func = staticmethod(lists.iflatten_func)
    if not lists.cpy_builtin:
        skip = "cpython extension isn't available"
