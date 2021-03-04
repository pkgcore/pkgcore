import os

from snakeoil.osutils import pjoin
from snakeoil.test import TestCase
from snakeoil.test.mixins import TempDirMixin

from pkgcore.fs import fs, livefs
from pkgcore.fs.contents import contentsSet


class FsObjsTest(TempDirMixin, TestCase):

    def check_attrs(self, obj, path, offset=None):
        if offset is None:
            st = os.lstat(path)
        else:
            st = os.lstat(offset + '/' + path)
        if offset is not None:
            self.assertTrue(
                path.startswith("/"),
                msg=f"path must be absolute, got {path!r}")
        self.assertEqual(obj.mode & 0o7777, st.st_mode & 0o7777)
        self.assertEqual(obj.uid, st.st_uid)
        self.assertEqual(obj.gid, st.st_gid)
        if fs.isreg(obj):
            if offset is None:
                self.assertEqual(obj.data.path, path)
            else:
                self.assertEqual(obj.data.path,
                    offset + path)

    def test_data_source(self):
        o = livefs.gen_obj("/tmp/etc/passwd", real_location="/etc/passwd")
        self.assertTrue(o.location, "/tmp/etc/passwd")
        self.assertTrue(o.data.path, "/etc/passwd")
        with open("/etc/passwd", "rb") as f:
            self.assertTrue(o.data.bytes_fileobj().read(), f.read())

    def test_gen_obj_reg(self):
        path = os.path.join(self.dir, "reg_obj")
        open(path, "w").close()
        o = livefs.gen_obj(path)
        self.assertTrue(fs.isreg(o))
        self.check_attrs(o, path)
        o2 = livefs.gen_obj(path, inode=None)
        self.check_attrs(o, path)
        self.assertNotEqual(o.inode, o2.inode)

    def test_gen_obj_dir(self):
        o = livefs.gen_obj(self.dir)
        self.assertTrue(fs.isdir(o))
        self.check_attrs(o, self.dir)

    def test_gen_obj_sym(self):
        path = os.path.join(self.dir, "test_sym")
        os.mkdir(path)
        src = os.path.join(path, "s")
        link = os.path.join(path, "t")
        open(src, "w").close()
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
        for x in files:
            open(x, "w").close()
        dirs = [os.path.normpath(os.path.join(path, x)) for x in [
                "a", "b", "c"]]
        for x in dirs:
            os.mkdir(x)
        dirs.append(path)
        for obj in livefs.iter_scan(path):
            self.assertInstance(obj, fs.fsBase)
            if fs.isreg(obj):
                self.assertTrue(obj.location in files)
            elif fs.isdir(obj):
                self.assertTrue(obj.location in dirs)
            else:
                raise Exception(f"unknown object popped up in testing dir, {obj!r}")
            self.check_attrs(obj, obj.location)
        # do offset verification now.
        offset = os.path.join(self.dir, "iscan")
        for obj in livefs.iter_scan(path, offset=offset):
            self.check_attrs(obj, obj.location, offset=offset)

        seen = []
        for obj in livefs.iter_scan(files[0]):
            self.check_attrs(obj, obj.location)
            seen.append(obj.location)
        self.assertEqual((files[0],), tuple(sorted(seen)))

    def test_sorted_scan(self):
        path = os.path.join(self.dir, "sorted_scan")
        os.mkdir(path)
        files = [os.path.normpath(os.path.join(path, x)) for x in
                 ["tmp", "blah", "dar"]]
        # cheap version of a touch.
        for x in files:
            open(x, "w").close()
        dirs = [os.path.normpath(os.path.join(path, x)) for x in [
                "a", "b", "c"]]
        for x in dirs:
            os.mkdir(x)

        # regular directory scanning
        sorted_files = livefs.sorted_scan(path)
        self.assertEqual(
            list([pjoin(path, x) for x in ['blah', 'dar', 'tmp']]),
            sorted_files)

        # nonexistent paths
        nonexistent_path = os.path.join(self.dir, 'foobar')
        sorted_files = livefs.sorted_scan(nonexistent_path)
        self.assertEqual(sorted_files, [])
        sorted_files = livefs.sorted_scan(nonexistent_path, nonexistent=True)
        self.assertEqual(sorted_files, [nonexistent_path])

    def test_sorted_scan_hidden(self):
        path = os.path.join(self.dir, "sorted_scan")
        os.mkdir(path)
        files = [os.path.normpath(os.path.join(path, x)) for x in
                 [".tmp", "blah",]]
        # cheap version of a touch.
        for x in files:
            open(x, "w").close()
        sorted_files = livefs.sorted_scan(path)
        assert list([pjoin(path, x) for x in ['.tmp', 'blah']]) == sorted_files
        sorted_files = livefs.sorted_scan(path, hidden=False)
        assert list([pjoin(path, x) for x in ['blah']]) == sorted_files

    def test_sorted_scan_backup(self):
        path = os.path.join(self.dir, "sorted_scan")
        os.mkdir(path)
        files = [os.path.normpath(os.path.join(path, x)) for x in ["blah", "blah~"]]
        # cheap version of a touch.
        for x in files:
            open(x, "w").close()
        sorted_files = livefs.sorted_scan(path)
        assert list([pjoin(path, x) for x in ['blah', 'blah~']]) == sorted_files
        sorted_files = livefs.sorted_scan(path, backup=False)
        assert list([pjoin(path, x) for x in ['blah']]) == sorted_files

    def test_relative_sym(self):
        f = os.path.join(self.dir, "relative-symlink-test")
        os.symlink("../sym1/blah", f)
        o = livefs.gen_obj(f)
        self.assertTrue(o.target == "../sym1/blah")

    def test_intersect(self):
        open(pjoin(self.dir, 'reg'), 'w').close()
        cset = contentsSet([fs.fsFile('reg', strict=False)])
        cset = cset.insert_offset(self.dir)
        self.assertEqual(contentsSet(livefs.intersect(cset)), cset)
        cset = contentsSet([fs.fsFile('reg/foon', strict=False),
            fs.fsFile('reg/dar', strict=False),
            fs.fsDir('reg/dir', strict=False)]).insert_offset(self.dir)
        self.assertEqual(list(livefs.intersect(cset)), [])
        cset = contentsSet([fs.fsDir('reg', strict=False)])
        self.assertEqual(list(livefs.intersect(cset)), [])
