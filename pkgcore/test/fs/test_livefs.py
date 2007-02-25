# Copyright: 2005-2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os
from pkgcore.test import TestCase

from pkgcore.fs import fs, gen_obj, iter_scan
from pkgcore.test.mixins import TempDirMixin


class FsObjsTest(TempDirMixin, TestCase):

    def check_attrs(self, obj, path, offset=None):
        if offset is None:
            st = os.lstat(path)
        else:
            st = os.lstat(offset + '/' + path)
        if offset is not None:
            self.assertTrue(path.startswith("/"),
                msg="path must be absolute, got %r" % path)
        self.assertEqual(obj.mode & 07777, st.st_mode & 07777)
        self.assertEqual(obj.uid, st.st_uid)
        self.assertEqual(obj.gid, st.st_gid)
        if fs.isreg(obj):
            if offset is None:
                self.assertEqual(obj.data.get_path(), path)
            else:
                self.assertEqual(obj.data.get_path(),
                    offset + path)

    def test_data_source(self):
        o = gen_obj("/tmp/etc/passwd", real_location="/etc/passwd")
        self.failUnless(o.location, "/tmp/etc/passwd")
        self.failUnless(o.data.get_path(), "/etc/passwd")
        self.failUnless(
            o.data.get_fileobj().read(), open("/etc/passwd", "r").read())

    def test_gen_obj_reg(self):
        path = os.path.join(self.dir, "reg_obj")
        open(path, "w")
        o = gen_obj(path)
        self.failUnless(fs.isreg(o))
        self.check_attrs(o, path)

    def test_gen_obj_dir(self):
        o = gen_obj(self.dir)
        self.failUnless(fs.isdir(o))
        self.check_attrs(o, self.dir)

    def test_gen_obj_sym(self):
        path = os.path.join(self.dir, "test_sym")
        os.mkdir(path)
        src = os.path.join(path, "s")
        link = os.path.join(path, "t")
        open(src, "w")
        os.symlink(src, link)
        obj = gen_obj(link)
        self.failUnless(isinstance(obj, fs.fsSymlink))
        self.check_attrs(obj, link)
        self.assertEqual(os.readlink(link), obj.target)

    def test_gen_obj_fifo(self):
        path = os.path.join(self.dir, "fifo")
        os.mkfifo(path)
        o = gen_obj(path)
        self.check_attrs(o, path)

    def test_iterscan(self):
        path = os.path.join(self.dir, "iscan")
        os.mkdir(path)
        files = [os.path.normpath(os.path.join(path, x)) for x in [
                "tmp", "blah", "dar"]]
        # cheap version of a touch.
        map(lambda x:open(x, "w"), files)
        dirs = [os.path.normpath(os.path.join(path, x)) for x in [
                "a", "b", "c"]]
        map(os.mkdir, dirs)
        dirs.append(path)
        for obj in iter_scan(path):
            self.failUnless(isinstance(obj, fs.fsBase))
            if fs.isreg(obj):
                self.failUnless(obj.location in files)
            elif fs.isdir(obj):
                self.failUnless(obj.location in dirs)
            else:
                raise Exception(
                    "unknown object popped up in testing dir, '%s'" % obj)
            self.check_attrs(obj, obj.location)
        # do offset verification now.
        offset = os.path.join(self.dir, "iscan")
        for obj in iter_scan(path, offset=offset):
            self.check_attrs(obj, obj.location, offset=offset)


    def test_relative_sym(self):
        f = os.path.join(self.dir, "relative-symlink-test")
        os.symlink("../sym1/blah", f)
        o = gen_obj(f)
        self.failUnless(o.target == "../sym1/blah")

