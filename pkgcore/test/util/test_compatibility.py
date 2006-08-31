# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.util import compatibility
from pkgcore.util.currying import post_curry

class mixin:
	def test_builtin_override(self):
		if self.func_name in __builtins__:
			self.assertIdentical(__builtins__[self.func_name],
								 getattr(compatibility, self.func_name))

	def check_func(self, result1, result2, test3, result3):
		i = iter(xrange(100))
		f = getattr(compatibility, self.func_name)
		self.assertEquals(f(x==3 for x in i), result1)
		self.assertEquals(i.next(), result2)
		self.assertEquals(f(test3), result3)

class AnyTest(unittest.TestCase, mixin):
	func_name = "any"
	test_any = post_curry(mixin.check_func, True, 4, (x==3 for x in xrange(2)), False)


class AllTest(unittest.TestCase, mixin):
	func_name = "all"
	test_all = post_curry(mixin.check_func, False, 1,
		(isinstance(x, int) for x in xrange(100)), True)
