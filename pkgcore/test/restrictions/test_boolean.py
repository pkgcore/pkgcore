# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from twisted.trial import unittest

from pkgcore.restrictions import boolean, restriction
from pkgcore.util import mappings


true = restriction.AlwaysBool(node_type='foo', negate=True)
false = restriction.AlwaysBool(node_type='foo', negate=False)


class AlwaysForcableBool(boolean.base):

	def force_True(self, action, *args):
		yield True

	match = force_False = force_True


class BaseTest(unittest.TestCase):

	def test_invalid_restrictions(self):
		self.assertRaises(TypeError, boolean.base, 42, node_type='foo')
		base = boolean.base(node_type='foo')
		self.assertRaises(TypeError, base.add_restriction, 42)
		self.assertRaises(TypeError, base.add_restriction)

	def test_init_finalize(self):
		final = boolean.base(true, node_type='foo', finalize=True)
		# TODO perhaps this should be more specific?
		self.assertRaises(Exception, final.add_restriction, false)

	def test_finalize(self):
		base = boolean.base(true, node_type='foo')
		base.add_restriction(false)
		base.finalize()
		# TODO perhaps this should be more specific?
		self.assertRaises(Exception, base.add_restriction, true)

	def test_base(self):
		base = boolean.base(true, false, node_type='foo')
		self.assertEquals(len(base), 2)
		self.assertEquals(list(base), [true, false])
		self.assertRaises(NotImplementedError, base.match, false)
		# TODO is the signature for these correct?
		self.assertRaises(NotImplementedError, base.force_False, false)
		self.assertRaises(NotImplementedError, base.force_True, false)
		self.assertIdentical(base[1], false)

	# TODO total_len? what does it do?

# TODO these tests are way too limited
class AndRestrictionTest(unittest.TestCase):

	def test_match(self):
		self.failUnless(boolean.AndRestriction(true, true, node_type='foo').match(None))
		self.failIf(
			boolean.AndRestriction(false, true, true, node_type='foo').match(None))
		self.failIf(
			boolean.AndRestriction(true, false, true, node_type='foo').match(None))

	def test_negate_match(self):
		self.failUnless(
			boolean.AndRestriction(false, true,
				node_type='foo', negate=True).match(None))
		self.failUnless(
			boolean.AndRestriction(true, false, 
				node_type='foo', negate=True).match(None))
		self.failUnless(
			boolean.AndRestriction(false, false, 
				node_type='foo', negate=True).match(None))
		self.failIf(
			boolean.AndRestriction(true, true,
				node_type='foo', negate=True).match(None))


class OrRestrictionTest(unittest.TestCase):

	def test_match(self):
		self.failUnless(boolean.OrRestriction(true, true, node_type='foo').match(None))
		self.failUnless(
			boolean.OrRestriction(false, true, false, node_type='foo').match(None))
		self.failUnless(
			boolean.OrRestriction(true, false, false, node_type='foo').match(None))
		self.failUnless(
			boolean.OrRestriction(false, false, true, node_type='foo').match(None))
		self.failIf(
			boolean.OrRestriction(false, false, node_type='foo').match(None))

	def test_negate_match(self):
		for x in ((true, false), (false, true), (true,true)):
			self.failIf(boolean.OrRestriction(node_type='foo', negate=True, *x).match(None))
		self.failUnless(
			boolean.OrRestriction(false, false, node_type='foo', negate=True).match(None))
