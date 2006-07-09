# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.util import caching
WeakInstMeta = caching.WeakInstMeta

class weak_inst(object):
	__metaclass__ = WeakInstMeta
	__inst_caching__ = True
	counter = 0
	def __new__(cls, *args):
		cls.counter += 1
		return object.__new__(cls)
	def __init__(self, *args):
		pass
	@classmethod
	def reset(cls):
		cls.counter = 0

class automatic_disabled_weak_inst(weak_inst):
	pass

class explicit_disabled_weak_inst(weak_inst):
	__inst_caching__ = False

class reenabled_weak_inst(automatic_disabled_weak_inst):
	__inst_caching__ = True

class TestWeakInstMeta(unittest.TestCase):

	def test_reuse(self, kls=weak_inst):
		kls.reset()
		o = kls()
		self.assertIdentical(o, kls())
		self.assertEqual(kls.counter, 1)
		del o
		kls()
		self.assertEqual(kls.counter, 2)

	def test_disabling_inst(self):
		weak_inst.reset()
		for x in (1, 2):
			o = weak_inst(disable_inst_caching=True)
			self.assertIdentical(weak_inst.counter, x)
		del o
		o = weak_inst()
		self.assertFalse(o is weak_inst(disable_inst_caching=True))

	def test_class_disabling(self):
		automatic_disabled_weak_inst.reset()
		self.assertTrue(automatic_disabled_weak_inst() is not automatic_disabled_weak_inst())
		self.assertTrue(explicit_disabled_weak_inst() is not explicit_disabled_weak_inst())

	def test_reenabled(self):
		self.test_reuse(reenabled_weak_inst)

	def test_uncachable(self):
		weak_inst.reset()
		class fake_warning(object):
			def warn(*a, **kw):
				pass
		
		class chuck_errors(object):
			def __init__(self, error):
				self.error = error
			def __hash__(self):
				raise self.error
		
		# silence warnings.
		w = caching.warnings
		try:
			caching.warnings = fake_warning()
			self.assertTrue(weak_inst([]) is not weak_inst([]))
			self.assertEqual(weak_inst.counter, 2)
			for x in (TypeError, NotImplementedError):
				self.assertTrue(weak_inst(chuck_errors(x)) is not 
					weak_inst(chuck_errors(x)))
		finally:
			caching.warnings = w

	def test_hash_collision(self):
		class BrokenHash(object):
			def __hash__(self):
				return 1
		self.assertNotIdentical(weak_inst(BrokenHash()),
								weak_inst(BrokenHash()))
