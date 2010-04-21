# Copyright: 2005-2009 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import os
from pkgcore.test import TestCase

from pkgcore.fs import fs, livefs
from pkgcore.fs.contents import contentsSet
from snakeoil.test.mixins import TempDirMixin
from snakeoil.osutils import pjoin


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
        o = livefs.gen_obj("/tmp/etc/passwd", real_location="/etc/passwd")
        self.assertTrue(o.location, "/tmp/etc/passwd")
        self.assertTrue(o.data.get_path(), "/etc/passwd")
        self.assertTrue(
            o.data.get_bytes_fileobj().read(), open("/etc/passwd", "rb").read())

    def test_gen_obj_reg(self):
        path = os.path.join(self.dir, "reg_obj")
        open(path, "w")
        o = livefs.gen_obj(path)
        self.assertTrue(fs.isreg(o))
        self.check_attrs(o, path)

    def test_gen_obj_dir(self):
        o = livefs.gen_obj(self.dir)
        self.assertTrue(fs.isdir(o))
        self.check_attrs(o, self.dir)

    def test_gen_obj_sym(self):
        path = os.path.join(self.dir, "test_sym")
        os.mkdir(path)
        src = os.path.join(path, "s")
        link = os.path.join(path, "t")
        open(src, "w")
        os.symlink(src, link)
        obj = livefs.gen_obj(link)
        self.assertInstance(obj, fs.fsSymlink)
        self.check_attrs(obj, link)
        self.assertEqual(os.readlink(link), obj.target)

    def test_gen_obj_fifo(self):
        path = os.path.join(self.dir, "fifo")
        os.mkfifo(path)
        o = livefs.gen_obj(path)
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
        for obj in livefs.iter_scan(path):
            self.assertInstance(obj, fs.fsBase)
            if fs.isreg(obj):
                self.assertTrue(obj.location in files)
            elif fs.isdir(obj):
                self.assertTrue(obj.location in dirs)
            else:
                raise Exception(
                    "unknown object popped up in testing dir, '%s'" % obj)
            self.check_attrs(obj, obj.location)
        # do offset verification now.
        offset = os.path.join(self.dir, "iscan")
        for obj in livefs.iter_scan(path, offset=offset):
            self.check_attrs(obj, obj.location, offset=offset)

    def test_relative_sym(self):
        f = os.path.join(self.dir, "relative-symlink-test")
        os.symlink("../sym1/blah", f)
        o = livefs.gen_obj(f)
        self.assertTrue(o.target == "../sym1/blah")

    def test_intersect(self):
        open(pjoin(self.dir, 'reg'), 'w')
        cset = contentsSet([fs.fsFile('reg', strict=False)])
        cset = cset.insert_offset(self.dir)
        self.assertEqual(contentsSet(livefs.intersect(cset)), cset)
        cset = contentsSet([fs.fsFile('reg/foon', strict=False),
            fs.fsFile('reg/dar', strict=False),
            fs.fsDir('reg/dir', strict=False)]).insert_offset(self.dir)
        self.assertEqual(list(livefs.intersect(cset)), [])
        cset = contentsSet([fs.fsDir('reg', strict=False)])
        self.assertEqual(list(livefs.intersect(cset)), [])
