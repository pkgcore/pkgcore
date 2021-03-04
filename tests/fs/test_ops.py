import os
import shutil

import pytest
from snakeoil.data_source import local_source
from snakeoil.osutils import pjoin
from snakeoil.test import TestCase
from snakeoil.test.mixins import TempDirMixin

from pkgcore.fs import contents, fs, livefs, ops


class VerifyMixin:

    def verify(self, obj, kwds, stat):
        for attr, keyword in (("st_mtime", "mtime"),
                              ("st_gid", "gid"),
                              ("st_uid", "uid")):
            if keyword in kwds:
                self.assertEqual(getattr(stat, attr), kwds[keyword],
                                 f"testing {keyword}")
        if "mode" in kwds:
            self.assertEqual((stat.st_mode & 0o4777), kwds["mode"])


class TestDefaultEnsurePerms(VerifyMixin, TempDirMixin, TestCase):

    def common_bits(self, creator_func, kls):
        kwds = {"mtime":0o1234, "uid":os.getuid(), "gid":os.getgid(),
                "mode":0o775, "dev":None, "inode":None}
        o = kls(pjoin(self.dir, "blah"), **kwds)
        creator_func(o.location)
        self.assertTrue(ops.default_ensure_perms(o))
        self.verify(o, kwds, os.stat(o.location))
        kwds["mode"] = 0o770
        o2 = kls(pjoin(self.dir, "blah"), **kwds)
        self.assertTrue(ops.default_ensure_perms(o2))
        self.verify(o2, kwds, os.stat(o.location))
        self.assertRaises(
            OSError,
            ops.default_ensure_perms, kls(pjoin(self.dir, "asdf"), **kwds))

    def test_dir(self):
        self.common_bits(os.mkdir, fs.fsDir)

    def test_file(self):
        self.common_bits(lambda s:open(s, "w").close(), fs.fsFile)


class TestDefaultMkdir(TempDirMixin, TestCase):

    def test_it(self):
        o = fs.fsDir(pjoin(self.dir, "mkdir_test"), strict=False)
        self.assertTrue(ops.default_mkdir(o))
        old_umask = os.umask(0)
        try:
            self.assertEqual((os.stat(o.location).st_mode & 0o4777), 0o777 & ~old_umask)
        finally:
            os.umask(old_umask)
        os.rmdir(o.location)
        o = fs.fsDir(pjoin(self.dir, "mkdir_test2"), strict=False, mode=0o750)
        self.assertTrue(ops.default_mkdir(o))
        self.assertEqual(os.stat(o.location).st_mode & 0o4777, 0o750)


class TestCopyFile(VerifyMixin, TempDirMixin, TestCase):

    def test_it(self):
        src = pjoin(self.dir, "copy_test_src")
        dest = pjoin(self.dir, "copy_test_dest")
        with open(src, "w") as f:
            f.writelines("asdf\n" for i in range(10))
        kwds = {"mtime":10321, "uid":os.getuid(), "gid":os.getgid(),
                "mode":0o664, "data":local_source(src), "dev":None,
                "inode":None}
        o = fs.fsFile(dest, **kwds)
        self.assertTrue(ops.default_copyfile(o))
        with open(dest, "r") as f:
            self.assertEqual("asdf\n" * 10, f.read())
        self.verify(o, kwds, os.stat(o.location))

    def test_sym_perms(self):
        curgid = os.getgid()
        group = [x for x in os.getgroups() if x != curgid]
        if not group or os.getuid() != 0:
            pytest.skip(
                "requires root privs for this test, or for this user to"
                "belong to more then one group"
            )
        group = group[0]
        fp = pjoin(self.dir, "sym")
        o = fs.fsSymlink(fp, mtime=10321, uid=os.getuid(), gid=group,
            mode=0o664, target='target')
        self.assertTrue(ops.default_copyfile(o))
        self.assertEqual(os.lstat(fp).st_gid, group)
        self.assertEqual(os.lstat(fp).st_uid, os.getuid())

    def test_puke_on_dirs(self):
        path = pjoin(self.dir, "puke_dir")
        self.assertRaises(TypeError,
            ops.default_copyfile,
            fs.fsDir(path, strict=False))
        os.mkdir(path)
        fp = pjoin(self.dir, "foon")
        open(fp, "w").close()
        f = livefs.gen_obj(fp)
        self.assertRaises(TypeError,
            livefs.gen_obj(fp).change_attributes(location=path))

        # test sym over a directory.
        f = fs.fsSymlink(path, fp, mode=0o644, mtime=0, uid=os.getuid(),
            gid=os.getgid())
        self.assertRaises(TypeError, ops.default_copyfile, f)
        os.unlink(fp)
        os.mkdir(fp)
        self.assertRaises(ops.CannotOverwrite, ops.default_copyfile, f)


class ContentsMixin(VerifyMixin, TempDirMixin, TestCase):

    entries_norm1 = {
        "file1":["reg"],
        "dir":["dir"],
        "dir/subdir":["dir"],
        "dir/file2":["reg"],
        "ldir":["sym", "dir/subdir"],
        "dir/lfile":["sym", "../file1"]
        }

    entries_rec1 = {
        "dir":["dir"],
        "dir/link":["sym", "../dir"]
        }

    def generate_tree(self, base, entries):
        s_ents = [(pjoin(base, k), entries[k]) for k in sorted(entries)]
        for k, v in s_ents:
            if v[0] == "dir":
                os.mkdir(k)
        for k, v in s_ents:
            if v[0] == "dir":
                pass
            elif v[0] == "reg":
                open(k, "w").close()
            elif v[0] == "sym":
                os.symlink(v[1], k)
            else:
                raise Exception(
                    f"generate_tree doesn't support type {v!r} yet: k {k!r}")

    def gen_dir(self, name):
        d = os.path.join(self.dir, name)
        if os.path.exists(d):
            shutil.rmtree(d)
        os.mkdir(d)
        return d


class Test_merge_contents(ContentsMixin):

    def generic_merge_bits(self, entries):
        src = self.gen_dir("src")
        self.generate_tree(src, entries)
        cset = livefs.scan(src, offset=src)
        dest = self.gen_dir("dest")
        self.assertTrue(ops.merge_contents(cset, offset=dest))
        self.assertEqual(livefs.scan(src, offset=src),
            livefs.scan(dest, offset=dest))
        return src, dest, cset

    def test_callback(self):
        for attr in dir(self):
            if not attr.startswith('entries') or 'fail' in attr:
                continue
            e = getattr(self, attr)
            if not isinstance(e, dict):
                continue
            src, dest, cset = self.generic_merge_bits(e)
            new_cset = contents.contentsSet(contents.offset_rewriter(dest, cset))
            s = set(new_cset)
            ops.merge_contents(cset, offset=dest, callback=s.remove)
            self.assertFalse(s)

    def test_dangling_symlink(self):
        src = self.gen_dir("src")
        self.generate_tree(src, {"dir":["dir"]})
        cset = livefs.scan(src, offset=src)
        dest = self.gen_dir("dest")
        os.symlink(pjoin(dest, "dest"), pjoin(dest, "dir"))
        self.assertTrue(ops.merge_contents(cset, offset=dest))
        self.assertEqual(cset, livefs.scan(src, offset=dest))

    def test_empty_overwrite(self):
        self.generic_merge_bits(self.entries_norm1)

    def test_recursive_links(self):
        self.generic_merge_bits(self.entries_rec1)

    def test_exact_overwrite(self):
        src, dest, cset = self.generic_merge_bits(self.entries_norm1)
        self.assertTrue(ops.merge_contents(cset, offset=dest))

    def test_sym_over_dir(self):
        path = pjoin(self.dir, "sym")
        fp = pjoin(self.dir, "trg")
        os.mkdir(path)
        # test sym over a directory.
        f = fs.fsSymlink(path, fp, mode=0o644, mtime=0, uid=os.getuid(),
            gid=os.getgid())
        cset = contents.contentsSet([f])
        self.assertRaises(ops.FailedCopy, ops.merge_contents, cset)
        self.assertTrue(fs.isdir(livefs.gen_obj(path)))
        os.mkdir(fp)
        ops.merge_contents(cset)

    def test_dir_over_file(self):
        # according to the spec, dirs can't be merged over files that
        # aren't dirs or symlinks to dirs
        path = pjoin(self.dir, "file2dir")
        open(path, 'w').close()
        d = fs.fsDir(path, mode=0o755, mtime=0, uid=os.getuid(), gid=os.getgid())
        cset = contents.contentsSet([d])
        self.assertRaises(ops.CannotOverwrite, ops.merge_contents, cset)


class Test_unmerge_contents(ContentsMixin):

    def generic_unmerge_bits(self, entries, img="img"):
        img = self.gen_dir(img)
        self.generate_tree(img, entries)
        cset = livefs.scan(img, offset=img)
        return img, cset

    def test_callback(self):
        for attr in dir(self):
            if not attr.startswith('entries') or 'fail' in attr:
                continue
            e = getattr(self, attr)
            if not isinstance(e, dict):
                continue
            img, cset = self.generic_unmerge_bits(e)
            s = set(contents.offset_rewriter(img, cset))
            ops.unmerge_contents(cset, offset=img, callback=s.remove)
            self.assertFalse(s, s)

    def test_empty_removal(self):
        img, cset = self.generic_unmerge_bits(self.entries_norm1)
        self.assertTrue(
            ops.unmerge_contents(cset, offset=os.path.join(self.dir, "dest")))

    def test_exact_removal(self):
        img, cset = self.generic_unmerge_bits(self.entries_norm1)
        self.assertTrue(ops.unmerge_contents(cset, offset=img))
        self.assertFalse(livefs.scan(img, offset=img))

    def test_lingering_file(self):
        img, cset = self.generic_unmerge_bits(self.entries_norm1)
        dirs = [k for k, v in self.entries_norm1.items() if v[0] == "dir"]
        fp = os.path.join(img, dirs[0], "linger")
        open(fp, "w").close()
        self.assertTrue(ops.unmerge_contents(cset, offset=img))
        self.assertTrue(os.path.exists(fp))
