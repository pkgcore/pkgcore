# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.util import compatibility


class AnyTest(unittest.TestCase):
	
	def test_check_for_builtin_any(self):
		if "any" in __builtins__:
			if compatibility.any is __builtins__.any:
				raise unittest.SkipTest("builtin any is being used")
			raise unittest.FailTest("builtin any is available, but not used")

	def test_any(self):
		i = iter(xrange(100))
		self.assertEquals(compatibility.any(x==3 for x in i), True)
		self.assertEquals(i.next(), 4, "any consumed more args then needed")
		self.assertEquals(compatibility.any(x==3 for x in i), False)

class AllTest(unittest.TestCase):

	def test_check_for_builtin_all(self):
		if "all" in __builtins__:
			if compatibility.all is __builtins__.all:
				raise unittest.SkipTest("builtin all is being used")
			raise unittest.FailTest("builtin all is available, but not used")

	def test_all(self):
		i = iter(xrange(100))
		self.assertEquals(compatibility.all(x==3 for x in i), False)
		self.assertEquals(i.next(), 1)
		self.assertEquals(compatibility.all(isinstance(x,int) for x in i), True)
