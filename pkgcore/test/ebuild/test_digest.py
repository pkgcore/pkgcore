# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.ebuild.digest import parse_digest
from pkgcore.chksum.errors import ParseChksumError
import tempfile, os

digest_contents = """MD5 98db1465629693fc434d4dc52db93838 Python-2.4.2.tar.bz2 7853169
RMD160 c511d2b76b5394742d285e71570a2bcd3c1fa871 Python-2.4.2.tar.bz2 7853169
SHA256 e163b95ee56819c0f3c58ef9278c30b9e49302c2f1a1917680ca894d33929f7e Python-2.4.2.tar.bz2 7853169
MD5 2fa54dd51b6a8f1c46e5baf741e90f7e python-2.4-patches-1.tar.bz2 7820
RMD160 313c0f4f4dea59290c42a9b2c8de1db159f1ca1b python-2.4-patches-1.tar.bz2 7820
SHA256 e22abe4394f1f0919aac429f155c00ec1b3fe94cdc302119059994d817cd30b5 python-2.4-patches-1.tar.bz2 7820"""

files = ["Python-2.4.2.tar.bz2", "python-2.4-patches-1.tar.bz2"]

class parse_digest_testcases(unittest.TestCase):

	@staticmethod
	def gen_digest(data=digest_contents, **flags):
		fn = tempfile.mktemp()
		open(fn, "w").write(data)
		try:
			d = parse_digest(fn, **flags)
		finally:
			os.unlink(fn)
		return d

	def test_parsing(self):
		d = self.gen_digest()
		self.assertEqual(sorted(d.keys()), sorted(files))
		d2 = d["Python-2.4.2.tar.bz2"]
		self.assertEqual(sorted(d2.keys()), sorted(["md5", "size", "rmd160", "sha256"]))
		for chf, sum in (("size", long(7853169)), ("md5", "98db1465629693fc434d4dc52db93838"),
			("rmd160", "c511d2b76b5394742d285e71570a2bcd3c1fa871"),
			("sha256", "e163b95ee56819c0f3c58ef9278c30b9e49302c2f1a1917680ca894d33929f7e")):
			self.assertEqual(d2[chf], sum)
		self.assertTrue(isinstance(d2["size"], long))

	def test_throw(self):
		self.assertRaises(ParseChksumError, self.gen_digest, digest_contents+"\nMD5 asdfasdfasdfasdf")
		self.assertEqual(len(self.gen_digest(digest_contents+"\nMD5 asdfasdf", throw_errors=False)), 2)
