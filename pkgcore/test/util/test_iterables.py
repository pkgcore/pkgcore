# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.util.iterables import expandable_chain, caching_iter


class ExpandableChainTest(unittest.TestCase):
	
	def test_normal_function(self):
		i = [iter(xrange(100)) for x in xrange(3)]
		e = expandable_chain()
		e.extend(i)
		self.assertEquals(list(e), range(100)*3)
		for x in i + [e]:
			self.assertRaises(StopIteration, x.next)

	def test_extending(self):
		e = expandable_chain()
		e.extend(xrange(100) for x in (1,2))
		self.assertEquals(list(e), range(100)*2)
		self.assertRaises(StopIteration, e.extend, [[]])

	def test_appending(self):
		e = expandable_chain()
		e.append(xrange(100))
		self.assertEquals(list(e), range(100))
		self.assertRaises(StopIteration, e.append, [])


class CachingIterTest(unittest.TestCase):

	def test_iter_consumption(self):
		i = iter(xrange(100))
		c = caching_iter(i)
		i2 = iter(c)
		[i2.next() for x in xrange(20)]
		self.assertEqual(i.next(), 20)
		# note we consumed one ourselves
		self.assertEqual(c[20], 21)
		list(c)
		self.assertRaises(StopIteration, i.next)
		self.assertEqual(list(c), range(20) + range(21, 100))

	def test_full_consumption(self):
		i = iter(xrange(100))
		c = caching_iter(i)
		self.assertEqual(list(c), range(100))
		# do it twice, to verify it returns properly
		self.assertEqual(list(c), range(100))
	
	def test_len(self):
		self.assertEqual(100, len(caching_iter(xrange(100))))

