# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2
# $Id:$


from twisted.trial import unittest

from portage.util import lists


class UnhashableComplex(complex):

    def __hash__(self):
        raise TypeError


class UniqueTest(unittest.TestCase):

    def test_unique(self):
        # silly
        self.assertEquals(lists.unique(()), [])
        # hashable
        self.assertEquals(sorted(lists.unique([1,1,2,3,2])), [1,2,3])
        # sortable
        self.assertEquals(sorted(lists.unique(
                    [[1, 2], [1, 3], [1, 2], [1, 3]])), [[1, 2], [1, 3]])
        # neither
        uc = UnhashableComplex
        res = lists.unique([uc(1, 0), uc(0, 1), uc(1, 0)])
        self.failUnless(
            res == [uc(1, 0), uc(0, 1)] or res == [uc(0, 1), uc(1, 0)], res)


class FlattenTest(unittest.TestCase):

    def test_flatten(self):
        self.assertEquals(lists.flatten([(1), (2, [3, 4])]), [1, 2, 3, 4])
        self.assertEquals(lists.flatten(()), [])
        self.assertEquals(
            lists.flatten(['foo', ('bar', 'baz')]),
            ['foo', 'bar', 'baz'])
