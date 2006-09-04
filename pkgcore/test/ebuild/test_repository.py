# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from twisted.trial import unittest
from pkgcore.ebuild import repository


class DelayedInvertedContainsTest(unittest.TestCase):

    def test_delayedinverted(self):
        gooddata = object()
        baddata = object()
        def func(value):
            # "data" pulled from enclosing scope when this is called
            self.assertIdentical(data, value)
            return (1, 2)

        # fail if func is called immediately
        data = baddata
        theset = repository.DelayedInvertedContains(func, gooddata)
        # func should be called now
        data = gooddata
        self.assertNotIn(1, theset)
        # but func should not be called again
        data = baddata
        self.assertIn(0, theset)
