# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore import chksum
from pkgcore.util.currying import post_curry
import tempfile, os

data = "afsd123klawerponzzbnzsdf;h89y23746123;haas"
multi = 40000
sums = {"rmd160":"b83ad488d624e7911f886420ab230f78f6368b9f",
	"size":long(len(data)*multi),
	"sha1":"63cd8cce8a1773dffb400ee184be3ec7d89791f5",
	"md5":"d17ea153bc57ba9e07298c5378664369",
	"sha256":"68ae37b45e4a4a5df252db33c0cbf79baf5916b5ff6fc15e8159163b6dbe3bae"}

class ChksumsTests(unittest.TestCase):
	def setUp(self):
		self.fn = tempfile.mktemp()
		f = open(self.fn,"w")
		for x in xrange(multi):
			f.write(data)
		f.close()
	
	def tearDown(self):
		try:
			os.unlink(self.fn)
		except IOError:
			pass
	
	def generic_check(self, chf_type):
		chf = chksum.get_handler(chf_type)
		self.assertEqual(chf(self.fn), sums[chf_type])

	locals().update([("test_%s" % x, post_curry(generic_check, x)) for x in 
		("rmd160", "sha1", "sha256", "md5")])
	del x
	
	def test_size(self):
		self.generic_check("size")
		self.assertEqual(isinstance(chksum.get_handler("size")(self.fn), long), True)
