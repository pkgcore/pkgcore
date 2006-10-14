# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os
from pkgcore.fs import fs
from pkgcore.test import TestCase
from pkgcore.interfaces.data_source import data_source
from pkgcore.chksum import get_chksums

class base(object):

    kls = None

    def make_obj(self, location="/tmp/foo", **kwds):
        kwds.setdefault("strict", False)
        return self.kls(location, **kwds)

    def test_init(self):
        raise NotImplementedError(self)

    test_init.todo = "implement..."
    test_change_attributes = test_init

    def test_init(self):
        mkobj = self.make_obj
        o = mkobj("/tmp/foo")
        self.assertEqual(o.location, "/tmp/foo")
        # we ignore real_location; test_real_location handles it.
        self.assertEqual(mkobj(mtime=100l).mtime, 100l)
        self.assertEqual(mkobj(mode=0660).mode, 0660)
        # ensure the highband stays in..
        self.assertEqual(mkobj(mode=042660).mode, 042660)
        self.assertEqual(mkobj(uid=0).uid, 0)
        self.assertEqual(mkobj(gid=0).gid, 0)
    
    def test_hash(self):
        # might seem odd, but done this way to avoid the any potential
        # false positives from str's hash returning the same
        d = {self.make_obj("/tmp/foo"):None}
        d[self.make_obj("/tmp/foo")]
    
    def test_real_location(self):
        self.assertEqual(self.make_obj("/tmp/foobar").real_location,
            "/tmp/foobar")
        self.assertEqual(self.make_obj("/tmp/foobar",
            real_location="/dar").real_location, "/dar")

    def test_eq(self):
        o = self.make_obj("/tmp/foo")
        self.assertEqual(o, self.make_obj("/tmp/foo"))
        self.assertNotEqual(o, self.make_obj("/tmp/foo2"))

    def test_setattr(self):
        o = self.make_obj()
        for attr in o.__attrs__:
            self.assertRaises(AttributeError, setattr, o, attr, "monkies")


class Test_fsFile(TestCase, base):

    kls = fs.fsFile

    def test_init(self):
        base.test_init(self)
        mkobj = self.make_obj
        o = mkobj("/etc/passwd")
        raw_data = open("/etc/passwd").read()
        self.assertEqual(o.data.get_fileobj().read(), raw_data)
        o = mkobj("/bin/this-file-should-not-exist-nor-be-read", 
            data_source=data_source(raw_data))
        self.assertEqual(o.data.get_fileobj().read(), raw_data)
        keys = o.chksums.keys()
        self.assertEqual([o.chksums[x] for x in keys],
            list(get_chksums(data_source(raw_data), *keys)))

        chksums = dict(o.chksums.iteritems())
        self.assertEqual(sorted(mkobj(chksums=chksums).chksums.iteritems()),
            sorted(chksums.iteritems()))


class Test_fsLink(TestCase, base):
    kls = fs.fsLink

    def make_obj(self, location="/tmp/foo", **kwds):
        target = kwds.pop("target", os.path.join(location, "target"))
        kwds.setdefault("strict", False)
        return self.kls(location, target, **kwds)

    def test_init(self):
        base.test_init(self)
        mkobj = self.make_obj
        self.assertEqual(mkobj(target="k9").target, "k9")
        self.assertEqual(mkobj(target="../foon").target, "../foon")

class Test_fsDev(TestCase, base):
    kls = fs.fsDev

    def test_init(self):
        base.test_init(self)
        mkobj = self.make_obj
        self.assertRaises(TypeError, mkobj, major=-1, strict=True)
        self.assertRaises(TypeError, mkobj, minor=-1, strict=True)
        self.assertEqual(mkobj(major=1).major, 1)
        self.assertEqual(mkobj(minor=1).minor, 1)


class Test_fsFifo(TestCase, base):
    kls = fs.fsFifo


class Test_fsDir(TestCase, base):
    kls = fs.fsDir
