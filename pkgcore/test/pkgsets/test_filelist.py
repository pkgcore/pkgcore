# Copyright: 2006-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import tempfile, os
from pkgcore.test import TestCase, protect_logging, callback_logger
from pkgcore.pkgsets import filelist
from pkgcore.ebuild.atom import atom
from pkgcore import log

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
        self.assertEqual(map(atom, (x.strip() for x in open(self.fn))),
            sorted(map(atom, ("dev-util/diffball", "=dev-util/bsdiff-0.4",
            "dev-util/foon", "=dev-util/lib-1"))))

    def test_remove(self):
        s = self.gen_pkgset("=dev-util/diffball-0.4\ndev-util/bsdiff")
        s.remove(atom("=dev-util/diffball-0.4"))
        s.flush()
        self.assertEqual(sorted(x.strip() for x in open(self.fn) if x.strip()),
            ["dev-util/bsdiff"])

    def test_subset_awareness(self):
        s = self.gen_pkgset("@world\ndev-util/bsdiff")
        self.assertRaises(ValueError, sorted, s)

    def test_ignore_comments(self):
        s = self.gen_pkgset("#foon\ndev-util/bsdiff")
        self.assertEqual([str(x) for x in s], ['dev-util/bsdiff'])


class TestWorldFile(TestFileList):

    kls = staticmethod(filelist.WorldFile)

    def test_add(self):
        s = self.gen_pkgset("dev-util/bsdiff")
        s.add(atom("dev-util/foon"))
        s.add(atom("=dev-util/lib-1"))
        s.add(atom("dev-util/mylib:2,3"))
        s.flush()
        self.assertEqual(sorted(x.strip() for x in open(self.fn)),
            sorted(("dev-util/bsdiff", "dev-util/foon", "dev-util/lib",
                "dev-util/mylib:2", "dev-util/mylib:3")))

    def test_remove(self):
        s = self.gen_pkgset("dev-util/diffball\ndev-util/bsdiff")
        s.remove(atom("=dev-util/diffball-0.4"))
        s.flush()
        self.assertEqual(sorted(x.strip() for x in open(self.fn) if x.strip()),
            ["dev-util/bsdiff"])

    @protect_logging(log.logging.root)
    def test_subset_awareness(self):
        callbacks = []
        log.logging.root.handlers = [callback_logger(callbacks.append)]
        s = self.gen_pkgset("@world\ndev-util/bsdiff")
        self.assertRaises(ValueError, sorted, s)

    @protect_logging(log.logging.root)
    def test_subset_awareness(self):
        callbacks = []
        log.logging.root.handlers = [callback_logger(callbacks.append)]
        s = self.gen_pkgset("@world\ndev-util/bsdiff")
        self.assertEqual([str(x) for x in s], ['dev-util/bsdiff'])
        self.assertIn("set item 'world'", str(callbacks[0]))
        
