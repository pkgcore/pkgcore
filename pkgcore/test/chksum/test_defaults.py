# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore import chksum
from pkgcore.interfaces.data_source import data_source, local_source
import tempfile, os

data = "afsd123klawerponzzbnzsdf;h89y23746123;haas"
multi = 40000

class ChksumTest(object):
    def setUp(self):
        try:
            self.chf = chksum.get_handler(self.chf_type)
        except KeyError:
            raise unittest.SkipTest(
                'no handler for %s, do you need to install PyCrypto?' % (
                    self.chf_type,))
        self.fn = tempfile.mktemp()
        f = open(self.fn,"w")
        for i in xrange(multi):
            f.write(data)
        f.close()

    def tearDown(self):
        try:
            os.unlink(self.fn)
        except IOError:
            pass

    def test_fp_check(self):
        self.assertEqual(self.chf(self.fn), self.sum)

    def test_fileobj_check(self):
        self.assertEqual(self.chf(open(self.fn, "r")), self.sum)

    def test_data_source_check(self):
        self.assertEqual(self.chf(local_source(self.fn)), self.sum)
        self.assertEqual(
            self.chf(data_source(open(self.fn, "r").read())), self.sum)


# trick: create subclasses for each checksum with a useful class name.
for chf_type, expectedsum in {
    "rmd160":"b83ad488d624e7911f886420ab230f78f6368b9f",
    "size":long(len(data)*multi),
    "sha1":"63cd8cce8a1773dffb400ee184be3ec7d89791f5",
    "md5":"d17ea153bc57ba9e07298c5378664369",
    "sha256":"68ae37b45e4a4a5df252db33c0cbf79baf5916b5ff6fc15e8159163b6dbe3bae",
    }.iteritems():
    globals()[chf_type + 'ChksumTest'] = type(
        chf_type + 'ChksumTest',
        (ChksumTest, unittest.TestCase),
        dict(chf_type=chf_type, sum=expectedsum))

del chf_type
