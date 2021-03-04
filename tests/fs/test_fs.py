import os

from snakeoil.chksum import get_chksums
from snakeoil.data_source import data_source
from snakeoil.osutils import normpath, pjoin
from snakeoil.test import TestCase
from snakeoil.test.mixins import tempdir_decorator

from pkgcore.fs import fs


class base:

    kls = None

    def make_obj(self, location="/tmp/foo", **kwds):
        kwds.setdefault("strict", False)
        return self.kls(location, **kwds)

    def test_basename(self):
        self.assertEqual(self.make_obj(location='/asdf').basename, 'asdf')
        self.assertEqual(self.make_obj(location='/a/b').basename, 'b')

    def test_dirname(self):
        self.assertEqual(self.make_obj(location='/asdf').dirname, '/')
        self.assertEqual(self.make_obj(location='/a/b').dirname, '/a')

    def test_location_normalization(self):
        for loc in ('/tmp/a', '/tmp//a', '/tmp//', '/tmp/a/..'):
            self.assertEqual(self.make_obj(location=loc).location,
                normpath(loc), reflective=False)

    def test_change_attributes(self):
        # simple test...
        o = self.make_obj("/foon")
        self.assertNotEqual(o, o.change_attributes(location="/nanners"))

    def test_init(self):
        mkobj = self.make_obj
        o = mkobj("/tmp/foo")
        self.assertEqual(o.location, "/tmp/foo")
        self.assertEqual(mkobj(mtime=100).mtime, 100)
        self.assertEqual(mkobj(mode=0o660).mode, 0o660)
        # ensure the highband stays in..
        self.assertEqual(mkobj(mode=0o42660).mode, 0o42660)
        self.assertEqual(mkobj(uid=0).uid, 0)
        self.assertEqual(mkobj(gid=0).gid, 0)

    def test_hash(self):
        # might seem odd, but done this way to avoid the any potential
        # false positives from str's hash returning the same
        d = {self.make_obj("/tmp/foo"):None}
        # ensure it's accessible without a KeyError
        d[self.make_obj("/tmp/foo")]

    def test_eq(self):
        o = self.make_obj("/tmp/foo")
        self.assertEqual(o, self.make_obj("/tmp/foo"))
        self.assertNotEqual(o, self.make_obj("/tmp/foo2"))

    def test_setattr(self):
        o = self.make_obj()
        for attr in o.__attrs__:
            self.assertRaises(AttributeError, setattr, o, attr, "monkies")

    @tempdir_decorator
    def test_realpath(self):
        # just to be safe, since this could trash some tests.
        self.dir = os.path.realpath(self.dir)
        os.mkdir(pjoin(self.dir, "test1"))
        obj = self.make_obj(location=pjoin(self.dir, "test1", "foon"))
        self.assertIdentical(obj, obj.realpath())
        os.symlink(pjoin(self.dir, "test1"), pjoin(self.dir, "test2"))
        obj = self.make_obj(location=pjoin(self.dir, "test2", "foon"))
        new_obj = obj.realpath()
        self.assertNotIdentical(obj, new_obj)
        self.assertEqual(new_obj.location, pjoin(self.dir, "test1", "foon"), reflective=False)
        os.symlink(pjoin(self.dir, "test3"), pjoin(self.dir, "nonexistent"))
        obj = self.make_obj(pjoin(self.dir, "nonexistent", "foon"))
        # path is incomplete; should still realpath it.
        new_obj = obj.realpath()
        self.assertNotIdentical(obj, new_obj)
        self.assertEqual(new_obj.location, pjoin(self.dir, "test3", "foon"))

    def test_default_attrs(self):
        self.assertEqual(self.make_obj(location="/adsf").mode, None)
        class tmp(self.kls):
            __default_attrs__ = self.kls.__default_attrs__.copy()
            __default_attrs__['tmp'] = lambda self2:getattr(self2, 'a', 1)
            __attrs__ = self.kls.__attrs__ + ('tmp',)
            __slots__ = ('a', 'tmp')
        try:
            self.kls = tmp
            self.assertEqual(self.make_obj('/adsf', strict=False).tmp, 1)
            t = self.make_obj('/asdf', a='foon', strict=False)
            self.assertEqual(t.tmp, "foon")
        finally:
            del self.kls


class Test_fsFile(TestCase, base):

    kls = fs.fsFile

    def test_init(self):
        base.test_init(self)
        mkobj = self.make_obj
        o = mkobj(__file__)
        with open(__file__) as f:
            raw_data = f.read()
        self.assertEqual(o.data.text_fileobj().read(), raw_data)
        o = mkobj("/bin/this-file-should-not-exist-nor-be-read",
            data=data_source(raw_data))
        self.assertEqual(o.data.text_fileobj().read(), raw_data)
        keys = list(o.chksums.keys())
        self.assertEqual([o.chksums[x] for x in keys],
            list(get_chksums(data_source(raw_data), *keys)))

        chksums = dict(iter(o.chksums.items()))
        self.assertEqual(sorted(mkobj(chksums=chksums).chksums.items()),
            sorted(chksums.items()))

    def test_chksum_regen(self):
        data_source = object()
        obj = self.make_obj(__file__)
        self.assertIdentical(obj.chksums,
            obj.change_attributes(location="/tpp").chksums)
        chksums1 = obj.chksums
        self.assertNotIdentical(chksums1,
            obj.change_attributes(data=data_source).chksums)

        self.assertIdentical(chksums1,
            obj.change_attributes(data=data_source,
                chksums=obj.chksums).chksums)

        obj2 = self.make_obj(__file__, chksums={1:2})
        self.assertIdentical(obj2.chksums,
            obj2.change_attributes(data=data_source).chksums)


class Test_fsLink(TestCase, base):
    kls = fs.fsLink

    def make_obj(self, location="/tmp/foo", **kwds):
        target = kwds.pop("target", pjoin(location, "target"))
        kwds.setdefault("strict", False)
        return self.kls(location, target, **kwds)

    def test_init(self):
        base.test_init(self)
        mkobj = self.make_obj
        self.assertEqual(mkobj(target="k9").target, "k9")
        self.assertEqual(mkobj(target="../foon").target, "../foon")

    def test_resolved_target(self):
        self.assertEqual(self.make_obj(location="/tmp/foon", target="dar").resolved_target,
            "/tmp/dar")
        self.assertEqual(self.make_obj(location="/tmp/foon", target="/dar").resolved_target,
            "/dar")

    def test_cmp(self):
        obj1 = self.make_obj(
            location='/usr/lib64/opengl/nvidia/lib/libnvidia-tls.so.1',
            target='../tls/libnvidia-tls.so.1')
        obj2 = self.make_obj(
            location='/usr/lib32/opengl/nvidia/lib/libGL.s',
            target='libGL.so.173.14.09')
        self.assertTrue(obj1 > obj2)
        self.assertTrue(obj2 < obj1)


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


class Test_Modules_Funcs(TestCase):

    def test_is_funcs(self):
        # verify it intercepts the missing attr
        self.assertFalse(fs.isdir(object()))
        self.assertFalse(fs.isreg(object()))
        self.assertFalse(fs.isfifo(object()))

        self.assertTrue(fs.isdir(fs.fsDir('/tmp', strict=False)))
        self.assertFalse(fs.isreg(fs.fsDir('/tmp', strict=False)))
        self.assertTrue(fs.isreg(fs.fsFile('/tmp', strict=False)))
