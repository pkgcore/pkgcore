# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from twisted.trial import unittest

from portage.restrictions import restriction


class BaseTest(unittest.TestCase):

    def test_base(self):
        base = restriction.base()
        self.assertEquals(len(base), 1)
        self.assertRaises(NotImplementedError, str, base)
        self.assertRaises(NotImplementedError, repr, base)
        self.assertRaises(NotImplementedError, hash, base)
        self.assertRaises(NotImplementedError, base.match)
        self.assertIdentical(None, base.intersect(base))


class AlwaysBoolTest(unittest.TestCase):

    def test_true(self):
        true = restriction.AlwaysBool('foo', True)
        false = restriction.AlwaysBool('foo', False)
        self.failUnless(true.match(false))
        self.failIf(false.match(true))
        self.assertEquals(str(true), "always 'True'")
        self.assertEquals(str(false), "always 'False'")
        self.assertNotEqual(hash(true), hash(false))
