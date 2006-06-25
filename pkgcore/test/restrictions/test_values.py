# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2


from twisted.trial import unittest
from pkgcore.restrictions import values

class TestStrExactMatch(unittest.TestCase):
	
	def test_case_sensitive(self):
		for x in (True, False):
			self.assertEquals(values.StrExactMatch("package", negate=not x).match("package"), x)
			self.assertEquals(values.StrExactMatch("portage", negate=not x).match("portage"), x)
			self.assertEquals(values.StrExactMatch("Package", negate=not x).match("package"), not x)
			self.assertEquals(values.StrExactMatch("diffball", negate=not x).match("bsdiff"), not x)

	def test_case_insensitve(self):
		for x in (True, False):
			self.assertEquals(values.StrExactMatch("Rsync", CaseSensitive=False, negate=not x).match("rsync"), x)
			self.assertEquals(values.StrExactMatch("rsync", CaseSensitive=False, negate=not x).match("RSYnC"), x)
			self.assertEquals(values.StrExactMatch("PackageA", CaseSensitive=False, negate=not x).match("package"), not x)
			self.assertEquals(values.StrExactMatch("diffball", CaseSensitive=False, negate=not x).match("bsdiff"), not x)
			
	def test__eq__(self):
		for negate in (True, False):
			self.assertEquals(values.StrExactMatch("rsync", negate=negate), values.StrExactMatch("rsync", negate=negate))
			for x in "Ca":
				self.assertNotEquals(values.StrExactMatch("rsync", negate=negate), \
					values.StrExactMatch("rsyn"+x, negate=negate))
			self.assertEquals(values.StrExactMatch("Rsync", CaseSensitive=False, negate=negate),  \
				values.StrExactMatch("rsync", CaseSensitive=False, negate=negate))


class TestStrGlobMatch(unittest.TestCase):

	def test_case_sensitive(self):
		for x in (True, False):
			self.assertEquals(values.StrGlobMatch("pack", negate=not x).match("package"), x)
			self.assertEquals(values.StrGlobMatch("package", negate=not x).match("package"), x)
			self.assertEquals(values.StrGlobMatch("port", negate=not x).match("portage"), x)
			self.assertEquals(values.StrGlobMatch("portagea", negate=not x).match("portage"), not x)
			self.assertEquals(values.StrGlobMatch("Package", negate=not x).match("package"), not x)
			self.assertEquals(values.StrGlobMatch("diffball", negate=not x).match("bsdiff"), not x)

	def test_case_insensitve(self):
		for x in (True, False):
			for y in ("c", ''):
				self.assertEquals(values.StrGlobMatch("Rsyn"+y, CaseSensitive=False, negate=not x).match("rsync"), x)
				self.assertEquals(values.StrGlobMatch("rsyn"+y, CaseSensitive=False, negate=not x).match("RSYnC"), x)
			self.assertEquals(values.StrGlobMatch("PackageA", CaseSensitive=False, negate=not x).match("package"), not x)
			self.assertEquals(values.StrGlobMatch("diffball", CaseSensitive=False, negate=not x).match("bsdiff"), not x)

	def test__eq__(self):
		for negate in (True, False):
			self.assertEquals(values.StrGlobMatch("rsync", negate=negate), values.StrGlobMatch("rsync", negate=negate))
			for x in "Ca":
				self.assertNotEquals(values.StrGlobMatch("rsync", negate=negate), \
					values.StrGlobMatch("rsyn"+x, negate=negate))
			self.assertEquals(values.StrGlobMatch("Rsync", CaseSensitive=False, negate=negate),  \
				values.StrGlobMatch("rsync", CaseSensitive=False, negate=negate))
		self.assertNotEqual(values.StrGlobMatch("rsync", negate=True), values.StrGlobMatch("rsync", negate=False))


class TestEqualityMatch(unittest.TestCase):

	def test_match(self):
		for x, y, ret in (("asdf", "asdf", True), ("asdf", "fdsa", False),
			(1, 1, True), (1,2, False),
			(list(range(2)), list(range(2)), True),
			(range(2), reversed(range(2)), False),
			(True, True, True),
			(True, False, False),
			(False, True, False)):
			for negate in (True, False):
				self.assertEquals(values.EqualityMatch(x, negate=negate).match(y), ret != negate, 
					msg="testing %s==%s, required %s, negate=%s" % (repr(x),repr(y), ret, negate))

	def test__eq__(self):
		for negate in (True, False):
			self.assertEqual(values.EqualityMatch("asdf", negate=negate), values.EqualityMatch("asdf", negate=negate))
			self.assertNotEqual(values.EqualityMatch(1, negate=negate), values.EqualityMatch(2, negate=negate))
		self.assertNotEqual(values.EqualityMatch("asdf", negate=True), values.EqualityMatch("asdf", negate=False))


class TestContainmentMatch(unittest.TestCase):

	def test_match(self):
		for x, y, ret in ((range(10), range(10), True), (range(10), [], False),
			(range(10), set(xrange(10)), True), (set(xrange(10)), range(10), True)):
			for negate in (True, False):
				self.assertEquals(values.ContainmentMatch(negate=negate, disable_inst_caching=True, *x).match(y), ret != negate)
		for negate in (True, False):
			self.assertEquals(values.ContainmentMatch(all=True, negate=negate, *range(10)).match(range(10)), not negate)
		self.assertEquals(values.ContainmentMatch("asdf").match("fdsa"), False)
		self.assertEquals(values.ContainmentMatch("asdf").match("asdf"), True)
		self.assertEquals(values.ContainmentMatch("asdf").match("aasdfa"), True)
		self.assertEquals(values.ContainmentMatch("asdf", "bzip").match("pbzip2"), True)


	def test__eq__(self):
		for negate in (True, False):
			self.assertEquals(values.ContainmentMatch(negate=negate, *range(100)), 
				values.ContainmentMatch(negate=negate, *range(100)), msg="range(100), negate=%s" % negate)
			self.assertNotEqual(values.ContainmentMatch(1, negate=not negate),
				values.ContainmentMatch(1, negate=negate))
			self.assertEqual(values.ContainmentMatch(1, 2, 3, all=True, negate=negate),
				values.ContainmentMatch(1, 2, 3, all=True, negate=negate))
			self.assertNotEqual(values.ContainmentMatch(1, 2, all=True, negate=negate),
				values.ContainmentMatch(1, 2, 3, all=True, negate=negate))
			self.assertNotEqual(values.ContainmentMatch(1, 2, 3, all=False, negate=negate),
				values.ContainmentMatch(1, 2, 3, all=True, negate=negate))
			
