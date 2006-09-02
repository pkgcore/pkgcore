# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from twisted.trial import unittest

from pkgcore.restrictions import restriction


class SillyBool(restriction.base):
	"""Extra stupid version of AlwaysBool to test base.force_{True,False}."""
	def match(self, something):
		return not self.negate


class BaseTest(unittest.TestCase):

	def test_base(self):
		base = restriction.base()
		self.assertEquals(len(base), 1)
		self.assertRaises(NotImplementedError, str, base)
		self.assertRaises(NotImplementedError, repr, base)
		self.failUnless(hash(base))
		self.assertRaises(NotImplementedError, base.match)
		self.assertIdentical(None, base.intersect(base))

	def test_force(self):
		true = SillyBool(negate=False)
		false = SillyBool(negate=True)
		self.failUnless(true.force_True(None))
		self.failIf(true.force_False(None))
		self.failIf(false.force_True(None))
		self.failUnless(false.force_False(None))


class AlwaysBoolTest(unittest.TestCase):

	def test_true(self):
		true = restriction.AlwaysBool('foo', True)
		false = restriction.AlwaysBool('foo', False)
		self.failUnless(true.match(false))
		self.failIf(false.match(true))
		self.assertEquals(str(true), "always 'True'")
		self.assertEquals(str(false), "always 'False'")
		self.assertNotEqual(hash(true), hash(false))
