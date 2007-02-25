# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase, SkipTest
from pkgcore import chksum
from pkgcore.interfaces.data_source import data_source, local_source
from pkgcore.util.currying import post_curry
import tempfile, os

data = "afsd123klawerponzzbnzsdf;h89y23746123;haas"
multi = 40000

class base(object):

    def get_chf(self):
        try:
            self.chf = chksum.get_handler(self.chf_type)
        except KeyError:
            raise SkipTest(
                'no handler for %s, do you need to install PyCrypto?' % (
                    self.chf_type,))

    def setUp(self):
        self.get_chf()
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
        self.assertEqual(self.chf(self.fn), self.expected_long)

    def test_fileobj_check(self):
        self.assertEqual(self.chf(open(self.fn, "r")), self.expected_long)

    def test_data_source_check(self):
        self.assertEqual(self.chf(local_source(self.fn)), self.expected_long)
        self.assertEqual(
            self.chf(data_source(open(self.fn, "r").read())), self.expected_long)

class ChksumTest(base):

    def test_str2long(self):
        self.assertEqual(self.chf.str2long(self.expected_str),
            self.expected_long)
        if self.chf_type == 'size':
            return
        for x in extra_chksums.get(self.chf_type, []):
            self.assertEqual(self.chf.str2long(x), long(x, 16))

    def test_long2str(self):
        self.assertEqual(self.chf.long2str(self.expected_long),
            self.expected_str)
        if self.chf_type == 'size':
            return
        for x in extra_chksums.get(self.chf_type, []):
            self.assertEqual(self.chf.long2str(long(x, 16)), x)

checksums = {
    "rmd160":"b83ad488d624e7911f886420ab230f78f6368b9f",
    "sha1":"63cd8cce8a1773dffb400ee184be3ec7d89791f5",
    "md5":"d17ea153bc57ba9e07298c5378664369",
    "sha256":"68ae37b45e4a4a5df252db33c0cbf79baf5916b5ff6fc15e8159163b6dbe3bae",
}
checksums.update((k, (long(v, 16), v)) for k, v in checksums.iteritems())
checksums["size"] = (long(len(data)*multi), str(long(len(data)*multi)))

extra_chksums = {
    "md5":
        ["2dfd84279314a178d0fa842af3a40e25577e1bc"]
}

for k, v in checksums.iteritems():
    extra_chksums.setdefault(k, []).extend((''.rjust(len(v[1]), '0'), '01'.rjust(len(v[1]), '0')))

# trick: create subclasses for each checksum with a useful class name.
for chf_type, expected in checksums.iteritems():
    expectedsum = expected[0]
    expectedstr = expected[1]
    globals()[chf_type + 'ChksumTest'] = type(
        chf_type + 'ChksumTest',
        (ChksumTest, TestCase),
        dict(chf_type=chf_type, expected_long=expectedsum, expected_str=expectedstr))

del chf_type


class get_chksums_test(base, TestCase):

    chfs = [k for k in sorted(checksums) if k != "size"]
    expected_long = [checksums[k][0] for k in chfs]
    del k

    def get_chf(self):
        self.chf = post_curry(chksum.get_chksums, *self.chfs)
