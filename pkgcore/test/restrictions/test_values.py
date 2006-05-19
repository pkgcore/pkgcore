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
