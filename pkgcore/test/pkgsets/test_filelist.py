# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase
from pkgcore.pkgsets import filelist
from pkgcore.ebuild.atom import atom
import tempfile, os

class TestFileList(TestCase):

    kls = staticmethod(filelist.FileList)

    def setUp(self):
        self.fn = tempfile.mktemp()

    def tearDown(self):
        try:
            os.unlink(self.fn)
        except IOError:
            pass

    def gen_pkgset(self, contents):
        open(self.fn, "w").write(contents)
        return self.kls(self.fn)

    def test_contains(self):
        self.assertIn(
            atom("x11-base/xorg-x11"), self.gen_pkgset("x11-base/xorg-x11"))

    def test_len(self):
        self.assertEqual(
            len(self.gen_pkgset("x11-base/xorg-x11\ndev-util/diffball")), 2)

    def test_iter(self):
        self.assertEqual(
            sorted(self.gen_pkgset("dev-util/diffball\ndev-util/bsdiff")),
            sorted(atom(x) for x in ["dev-util/diffball", "dev-util/bsdiff"]))

    def test_add(self):
        s = self.gen_pkgset("dev-util/diffball\n=dev-util/bsdiff-0.4")
        s.add(atom("dev-util/foon"))
        s.add(atom("=dev-util/lib-1"))
        s.flush()
        self.assertEqual(sorted(x.strip() for x in open(self.fn)),
            sorted(("dev-util/diffball", "=dev-util/bsdiff-0.4",
            "dev-util/foon", "=dev-util/lib-1")))

    def test_remove(self):
        s = self.gen_pkgset("=dev-util/diffball-0.4\ndev-util/bsdiff")
        s.remove(atom("=dev-util/diffball-0.4"))
        s.flush()
        self.assertEqual(sorted(x.strip() for x in open(self.fn) if x.strip()),
            ["dev-util/bsdiff"])


class TestWorldFile(TestFileList):

    kls = staticmethod(filelist.WorldFile)

    def test_add(self):
        s = self.gen_pkgset("dev-util/bsdiff")
        s.add(atom("dev-util/foon"))
        s.add(atom("=dev-util/lib-1"))
        s.flush()
        self.assertEqual(sorted(x.strip() for x in open(self.fn)),
            sorted(("dev-util/bsdiff", "dev-util/foon", "dev-util/lib")))

    def test_remove(self):
        s = self.gen_pkgset("dev-util/diffball\ndev-util/bsdiff")
        s.remove(atom("=dev-util/diffball-0.4"))
        s.flush()
        self.assertEqual(sorted(x.strip() for x in open(self.fn) if x.strip()),
            ["dev-util/bsdiff"])

