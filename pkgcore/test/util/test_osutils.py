# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

import os, grp, stat, fcntl
from itertools import izip

from pkgcore.test import TestCase, SkipTest
from pkgcore.util import osutils
from pkgcore.util.osutils import native_readdir
from pkgcore.test.mixins import TempDirMixin

pjoin = osutils.pjoin

class NativeListDirTest(TempDirMixin):

    module = native_readdir

    def setUp(self):
        TempDirMixin.setUp(self)
        self.subdir = pjoin(self.dir, 'dir')
        os.mkdir(self.subdir)
        f = open(pjoin(self.dir, 'file'), 'w')
        f.close()
        os.mkfifo(pjoin(self.dir, 'fifo'))

    def test_listdir(self):
        self.assertEqual(['dir', 'fifo', 'file'],
                          sorted(self.module.listdir(self.dir)))
        self.assertEqual([], self.module.listdir(self.subdir))

    def test_listdir_dirs(self):
        self.assertEqual(['dir'], self.module.listdir_dirs(self.dir))
        self.assertEqual([], self.module.listdir_dirs(self.subdir))

    def test_listdir_files(self):
        self.assertEqual(['file'], self.module.listdir_files(self.dir))
        self.assertEqual([], self.module.listdir_dirs(self.subdir))

    def test_missing(self):
        for func in (
            self.module.listdir,
            self.module.listdir_dirs,
            self.module.listdir_files,
            ):
            self.assertRaises(OSError, func, pjoin(self.dir, 'spork'))

    def test_dangling_sym(self):
        os.symlink("foon", pjoin(self.dir, "monkeys"))
        self.assertEqual(["file"], self.module.listdir_files(self.dir))

try:
    # No name "readdir" in module osutils
    # pylint: disable-msg=E0611
    from pkgcore.util.osutils import _readdir
except ImportError:
    _readdir = None

class CPyListDirTest(NativeListDirTest):
    module = _readdir
    if _readdir is None:
        skip = "cpython extension isn't available"

class EnsureDirsTest(TempDirMixin, TestCase):

    def check_dir(self, path, uid, gid, mode):
        self.failUnless(os.path.isdir(path))
        st = os.stat(path)
        self.failUnlessEqual(stat.S_IMODE(st.st_mode), mode,
                             '0%o != 0%o' % (stat.S_IMODE(st.st_mode), mode))
        self.failUnlessEqual(st.st_uid, uid)
        self.failUnlessEqual(st.st_gid, gid)


    def test_ensure_dirs(self):
        # default settings
        path = pjoin(self.dir, 'foo', 'bar')
        self.failUnless(osutils.ensure_dirs(path))
        self.check_dir(path, os.geteuid(), os.getegid(), 0777)

    def test_minimal_nonmodifying(self):
        path = pjoin(self.dir, 'foo', 'bar')
        self.failUnless(osutils.ensure_dirs(path, mode=0755))
        os.chmod(path, 0777)
        self.failUnless(osutils.ensure_dirs(path, mode=0755, minimal=True))
        self.check_dir(path, os.geteuid(), os.getegid(), 0777)

    def test_minimal_modifying(self):
        path = pjoin(self.dir, 'foo', 'bar')
        self.failUnless(osutils.ensure_dirs(path, mode=0750))
        self.failUnless(osutils.ensure_dirs(path, mode=0005, minimal=True))
        self.check_dir(path, os.geteuid(), os.getegid(), 0755)

    def test_create_unwritable_subdir(self):
        path = pjoin(self.dir, 'restricted', 'restricted')
        # create the subdirs without 020 first
        self.failUnless(osutils.ensure_dirs(os.path.dirname(path)))
        self.failUnless(osutils.ensure_dirs(path, mode=0020))
        self.check_dir(path, os.geteuid(), os.getegid(), 0020)
        # unrestrict it
        osutils.ensure_dirs(path)
        self.check_dir(path, os.geteuid(), os.getegid(), 0777)

    def test_mode(self):
        path = pjoin(self.dir, 'mode', 'mode')
        self.failUnless(osutils.ensure_dirs(path, mode=0700))
        self.check_dir(path, os.geteuid(), os.getegid(), 0700)
        # unrestrict it
        osutils.ensure_dirs(path)
        self.check_dir(path, os.geteuid(), os.getegid(), 0777)

    def test_gid(self):
        # abuse the portage group as secondary group
        portage_gid = grp.getgrnam('portage').gr_gid
        if portage_gid not in os.getgroups():
            raise SkipTest('you are not in the portage group')
        path = pjoin(self.dir, 'group', 'group')
        self.failUnless(osutils.ensure_dirs(path, gid=portage_gid))
        self.check_dir(path, os.geteuid(), portage_gid, 0777)
        self.failUnless(osutils.ensure_dirs(path))
        self.check_dir(path, os.geteuid(), portage_gid, 0777)
        self.failUnless(osutils.ensure_dirs(path, gid=os.getegid()))
        self.check_dir(path, os.geteuid(), os.getegid(), 0777)


class Test_abspath(TempDirMixin, TestCase):
    
    func = staticmethod(osutils.abspath)
    
    def test_it(self):
        trg = pjoin(self.dir, "foon")
        sym = pjoin(self.dir, "spork")
        os.symlink(trg, sym)
        self.assertRaises(OSError, self.func, trg)
        self.assertEqual(trg, self.func(sym))
        open(trg, 'w')
        self.assertEqual(trg, self.func(sym))
        self.assertEqual(trg, self.func(trg))


class Test_abssymlink(TempDirMixin, TestCase):

    def test_it(self):
        target = pjoin(self.dir, 'target')
        linkname = pjoin(self.dir, 'link')
        os.mkdir(target)
        os.symlink('target', linkname)
        self.assertEqual(osutils.abssymlink(linkname), target)


class Native_NormPathTest(TestCase):

    func = staticmethod(osutils.native_normpath)

    def test_normpath(self):
        f = self.func
        self.assertEqual(f('/foo/'), '/foo')
        self.assertEqual(f('//foo/'), '/foo')
        self.assertEqual(f('//foo/.'), '/foo')
        self.assertEqual(f('//..'), '/')
        self.assertEqual(f('//..//foo'), '/foo')
        self.assertEqual(f('/foo/..'), '/')
        self.assertEqual(f('..//foo'), '../foo')
        self.assertEqual(f('.//foo'), 'foo')
        self.assertEqual(f('//foo/.///somewhere//..///bar//'), '/foo/bar')


class Cpy_NormPathTest(Native_NormPathTest):

    func = staticmethod(osutils.normpath)
    if osutils.normpath is osutils.native_normpath:
        skip = "extension isn't compiled"


class Cpy_JoinTest(TestCase):

    if osutils.join is osutils.native_join:
        skip = "extension isn't compiled"

    def assertSame(self, val):
        self.assertEqual(osutils.native_join(*val),
            osutils.join(*val),
            msg="for %r, expected %r, got %r" % (val,
                osutils.native_join(*val),
                osutils.join(*val)))

    def test_reimplementation(self):
        map(self.assertSame, [
            ["", "foo"],
            ["foo", "dar"],
            ["foo", "/bar"],
            ["/bar", "dar"],
            ["/bar", "../dar"],
            ["", "../dar"]
            ])


# TODO: more error condition testing
class FsLockTest(TempDirMixin, TestCase):

    def test_nonexistant(self):
        self.assertRaises(osutils.NonExistant, osutils.FsLock,
            pjoin(self.dir, 'missing'))

    def test_locking(self):
        path = pjoin(self.dir, 'lockfile')
        lock = osutils.FsLock(path, True)
        # do this all non-blocking to avoid hanging tests
        self.failUnless(lock.acquire_read_lock(False))
        # file should exist now
        f = open(path)
        # acquire and release a read lock
        fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
        fcntl.flock(f, fcntl.LOCK_UN | fcntl.LOCK_NB)
        # we can't acquire an exclusive lock
        self.assertRaises(
            IOError, fcntl.flock, f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock.release_read_lock()
        # but now we can
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.failIf(lock.acquire_read_lock(False))
        self.failIf(lock.acquire_write_lock(False))
        fcntl.flock(f, fcntl.LOCK_UN | fcntl.LOCK_NB)
        # acquire an exclusive/write lock
        self.failUnless(lock.acquire_write_lock(False))
        self.assertRaises(
            IOError, fcntl.flock, f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # downgrade to read lock
        self.failUnless(lock.acquire_read_lock())
        fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
        fcntl.flock(f, fcntl.LOCK_UN | fcntl.LOCK_NB)
        self.assertRaises(
            IOError, fcntl.flock, f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # and release
        lock.release_read_lock()
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(f, fcntl.LOCK_UN | fcntl.LOCK_NB)

        self.failUnless(lock.acquire_write_lock(False))
        lock.release_write_lock()
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(f, fcntl.LOCK_UN | fcntl.LOCK_NB)


class Test_readfile(TempDirMixin, TestCase):

    # note no trailing newline.
    line_content = "\n".join(str(x) for x in xrange(100))
    func = staticmethod(osutils.native_readfile)

    largefile_testing_len = 2**17

    def setUp(self):
        TempDirMixin.setUp(self)
        self.fp = pjoin(self.dir, "foon")
        open(self.fp, 'w').write(self.line_content)

    def test_it(self):
        self.assertRaises(IOError, self.func, self.fp+"2")
        self.assertRaises(IOError, self.func, self.fp+"2", False)
        self.assertEqual(None, self.func(self.fp+"2", True))
        self.assertEqual(self.line_content, self.func(self.fp))
        # test big files; forces the cpy to switch over to mmap
        
        f = open(self.fp, "a")
        # keep in mind, we already have a line in the file.
        count = self.largefile_testing_len / len(self.line_content)
        for x in xrange(count -1):
            f.write(self.line_content)
        f.close()
        self.assertEqual(self.line_content * count, self.func(self.fp),
            msg="big file failed; len(%r) must equal len(%r)" % 
                (os.stat(self.fp).st_size, len(self.line_content) * count))


class Test_cpy_readfile(Test_readfile):
    
    if osutils.native_readfile is osutils.readfile:
        skip = "cpython extension not available"
    else:
        func = staticmethod(osutils.readfile)


# mostly out of lazyness, we derive directly from test_readfile instead of 
# splitting out a common base.  whoever changes readfile, gets to do the split 
# ;)

class Test_readlines(Test_readfile):
    
    func = staticmethod(osutils.native_readlines)
    lines = Test_readfile.line_content.split("\n")
    nlines = [x+"\n" for x in lines]
    nlines[-1] = nlines[-1].rstrip("\n")

    def assertList(self, expected, got):
        if not isinstance(expected, list):
            expected = list(expected)
        if not isinstance(got, list):
            got = list(got)
        self.assertEqual(len(expected), len(got))
        for idx, tup in enumerate(izip(expected, got)):
            self.assertEqual(tup[0], tup[1], 
                msg="expected %r, got %r for item %i" %
                    (tup[0], tup[1], idx))

    def test_it(self):
        func = self.func
        fp = self.fp
        bad_fp = "%s2" % fp
        
        self.assertRaises(IOError, func, bad_fp)
        # check defaults for none_on_missing, and swallow_missing
        self.assertRaises(IOError, func, bad_fp, False, False)
        self.assertRaises(IOError, func, bad_fp, False, False, False)
        # ensure non_on_missing=True && swallow_missing=False pukes
        self.assertRaises(IOError, func, bad_fp, False, False, True)
        
        # the occasional True as the first arg is ensuring strip_newlines
        # isn't doing anything.
        
        self.assertEqual(None, func(bad_fp, False, True, True))
        self.assertList([], func(bad_fp, False, True, False))
        self.assertList([], func(bad_fp, True, True, False))
        
        self.assertList(self.lines, func(fp))
        self.assertList(self.lines, func(fp, True))
        self.assertList(self.nlines, func(fp, False, False, False))
        
        # check it does produce an extra line for trailing newline.
        open(fp, 'a').write("\n")
        self.assertList([x+"\n" for x in self.lines], func(fp, False))
        self.assertList(self.lines+[], func(fp))
        self.assertList(self.lines+[], func(fp, True))

        # test big files.
        count = self.largefile_testing_len / len(self.line_content)
        f = open(self.fp, 'a')
        for x in xrange(count - 1):
            f.write(self.line_content+"\n")
        f.close()
        self.assertList(self.lines * count, func(fp))
        self.assertList(self.lines * count, func(fp, True))
        l = [x + "\n" for x in self.lines] * count
        self.assertList([x +"\n" for x in self.lines] * count,
            func(fp, False))
        self.assertList(self.lines * count, func(fp))
        self.assertList(self.lines * count, func(fp, True))
        

    def test_mtime(self):
        cur = os.stat_float_times()
        try:
            for x in (False, True):
                os.stat_float_times(False)
                self.assertEqual(os.stat(self.fp).st_mtime,
                    self.func(self.fp, x).mtime)

                os.stat_float_times(True)
                self.assertEqual(os.stat(self.fp).st_mtime,
                    self.func(self.fp, x).mtime)

            # ensure that when swallow, but not none_on_missing, mtime is None
            self.assertEqual(self.func(self.fp+"2", False, True, False).mtime,
                None)

        finally:
            os.stat_float_times(cur)


class Test_cpy_readlines(Test_readlines):

    if osutils.native_readlines is osutils.readlines:
        skip = "cpy extension isn't available"
    else:
        func = staticmethod(osutils.readlines)
