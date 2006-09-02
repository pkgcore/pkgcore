# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from twisted.trial import unittest
from pkgcore.restrictions import packages, values


class AlwaysSelfIntersect(values.base):
	def intersect(self, other):
		return self


class DummyIntersectingValues(values.base):

	"""Helper to test PackageRestriction.intersect."""

	def __init__(self, val, iself=False):
		self.val = val

	def intersect(self, other):
		return DummyIntersectingValues((self.val, other.val))


class PackageRestrictionTest(unittest.TestCase):

	def test_eq(self):
		self.assertEquals(
			packages.PackageRestriction('one', values.AlwaysTrue),
			packages.PackageRestriction('one', values.AlwaysTrue))
		self.assertNotEquals(
			packages.PackageRestriction('one', values.AlwaysTrue),
			packages.PackageRestriction('one', values.AlwaysTrue, negate=True))
		self.assertNotEquals(
			packages.PackageRestriction('one', values.AlwaysTrue),
			packages.PackageRestriction('two', values.AlwaysTrue))
		self.assertNotEquals(
			packages.PackageRestriction('one', values.AlwaysTrue, negate=True),
			packages.PackageRestriction('one', values.AlwaysFalse, negate=True))

	def test_intersect(self):
		alwaysSelf = AlwaysSelfIntersect()
		p1 = packages.PackageRestriction('one', alwaysSelf)
		p1n = packages.PackageRestriction('one', alwaysSelf, negate=True)
		p2 = packages.PackageRestriction('two', alwaysSelf)
		self.assertIdentical(p1, p1.intersect(p1))
		self.assertIdentical(None, p1.intersect(p2))
		self.assertIdentical(None, p1n.intersect(p1))

		for negate in (False, True):
			d1 = packages.PackageRestriction(
				'one', DummyIntersectingValues(1), negate=negate)
			d2 = packages.PackageRestriction(
				'one', DummyIntersectingValues(2), negate=negate)
			i1 = d1.intersect(d2)
			self.failUnless(i1)
			self.assertEquals((1, 2), i1.restriction.val)
			self.assertEquals(negate, i1.negate)
			self.assertEquals('one', i1.attr)
