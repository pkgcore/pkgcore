# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.util import dependant_methods as dm
from pkgcore.util import currying

class TestDependantMethods(unittest.TestCase):

	@staticmethod
	def generate_instance(methods, dependencies):
		class c(object):
			__metaclass__ = dm.ForcedDepends
			stage_depends = dict(dependencies)

		for k, v in methods.iteritems():
			setattr(c, k, v)

		return c()

	@staticmethod
	def f(self, l, x, val=True):
		l.append(x)
		return val

	def test_return_checking(self):
		results = []
		o = self.generate_instance(
			dict((str(x), currying.post_curry(self.f, results, x)) for x in range(10)),
			dict((str(x), str(x - 1)) for x in xrange(1, 10)))
		getattr(o, "9")()
		self.assertEqual(results, range(10))
		results = []
		o = self.generate_instance(
			dict((str(x), currying.post_curry(self.f, results, x, False)) for x in range(10)),
			dict((str(x), str(x - 1)) for x in xrange(1, 10)))
		getattr(o, "9")()
		self.assertEqual(results, [0])
		getattr(o, "9")()
		self.assertEqual(results, [0, 0])

	def test_stage_awareness(self):
		results = []
		o = self.generate_instance(
			dict((str(x), currying.post_curry(self.f, results, x)) for x in range(10)),
			dict((str(x), str(x - 1)) for x in xrange(1, 10)))
		getattr(o, "1")()
		self.assertEqual(results, [0, 1])
		getattr(o, "2")()
		self.assertEqual(results, [0, 1, 2])
		getattr(o, "2")()
		self.assertEqual(results, [0, 1, 2])

	def test_stage_depends(self):
		results = []
		methods = dict((str(x), currying.post_curry(self.f, results, x)) for x in range(10))
		deps = dict((str(x), str(x - 1)) for x in xrange(1, 10))
		deps["1"] = ["0", "a"]
		methods["a"] = currying.post_curry(self.f, results, "a")
		o = self.generate_instance(methods, deps)
		getattr(o, "1")()
		self.assertEqual(results, [0, "a", 1])
		getattr(o, "2")()
		self.assertEqual(results, [0, "a", 1, 2])
