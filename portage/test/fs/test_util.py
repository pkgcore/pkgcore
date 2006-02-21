# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id:$


import os
import grp
import stat
import fcntl
import shutil
import tempfile

from twisted.trial import unittest

from portage.fs import util


class TempDirMixin(object):

	def setUp(self):
		self.dir = tempfile.mkdtemp()

	def tearDown(self):
		# change permissions back or rmtree can't kill it
		for root, dirs, files in os.walk(self.dir):
			for dir in dirs:
				os.chmod(os.path.join(root, dir), 0777)
		shutil.rmtree(self.dir)
	

class EnsureDirsTest(TempDirMixin, unittest.TestCase):

	def checkDir(self, path, uid, gid, mode):
		self.failUnless(os.path.isdir(path))
		st = os.stat(path)
		self.failUnlessEqual(stat.S_IMODE(st.st_mode), mode)
		self.failUnlessEqual(st.st_uid, uid)
		self.failUnlessEqual(st.st_gid, gid)


	def test_ensure_dirs(self):
		# default settings
		path = os.path.join(self.dir, 'foo', 'bar')
		self.failUnless(util.ensure_dirs(path))
		self.checkDir(path, os.geteuid(), os.getegid(), 0777)

	def test_ensure_dirs_minimal_nonmodifying(self):
		path = os.path.join(self.dir, 'foo', 'bar')
		self.failUnless(util.ensure_dirs(path, mode=0755))
		os.chmod(path, 0777)
		self.failUnless(util.ensure_dirs(path, mode=0755, minimal=True))
		self.checkDir(path, os.geteuid(), os.getegid(), 0777)

	def test_ensure_dirs_minimal_modifying(self):
		path = os.path.join(self.dir, 'foo', 'bar')
		self.failUnless(util.ensure_dirs(path, mode=0750))
		self.failUnless(util.ensure_dirs(path, mode=0005, minimal=True))
		self.checkDir(path, os.geteuid(), os.getegid(), 0755)

	def test_create_unwritable_subdir(self):
		path = os.path.join(self.dir, 'restricted', 'restricted')
		# create the subdirs without 020 first
		self.failUnless(util.ensure_dirs(os.path.dirname(path)))
		self.failUnless(util.ensure_dirs(path, mode=0020))
		self.checkDir(path, os.geteuid(), os.getegid(), 0020)
		# unrestrict it
		util.ensure_dirs(path)
		self.checkDir(path, os.geteuid(), os.getegid(), 0777)

	def test_mode(self):
		path = os.path.join(self.dir, 'mode', 'mode')
		self.failUnless(util.ensure_dirs(path, mode=0700))
		self.checkDir(path, os.geteuid(), os.getegid(), 0700)
		# unrestrict it
		util.ensure_dirs(path)
		self.checkDir(path, os.geteuid(), os.getegid(), 0777)

	def test_gid(self):
		# abuse the portage group as secondary group
		portage_gid = grp.getgrnam('portage')[2]
		if portage_gid not in os.getgroups():
			raise unittest.SkipTest('you are not in the portage group')
		path = os.path.join('group', 'group')
		self.failUnless(util.ensure_dirs(path, gid=portage_gid))
		self.checkDir(path, os.geteuid(), portage_gid, 0777)
		self.failUnless(util.ensure_dirs(path))
		self.checkDir(path, os.geteuid(), portage_gid, 0777)
		self.failUnless(util.ensure_dirs(path, gid=os.getegid()))
		self.checkDir(path, os.geteuid(), os.getegid(), 0777)
		

class SymlinkTest(TempDirMixin, unittest.TestCase):

	def test_abssymlink(self):
		target = os.path.join(self.dir, 'target')
		linkname = os.path.join(self.dir, 'link')
		os.mkdir(target)
		os.symlink('target', linkname)
		self.assertEquals(util.abssymlink(linkname), target)
		

class NormPathTest(unittest.TestCase):

	def test_normpath(self):
		self.assertEquals(
			util.normpath('//foo/.///somewhere//..///bar//'), '/foo/bar')


# TODO: more error condition testing
class FsLockTest(TempDirMixin, unittest.TestCase):

	def test_nonexistant(self):
		self.assertRaises(
			util.NonExistant, util.FsLock, os.path.join(self.dir, 'missing'))
	
	def test_locking(self):
		path = os.path.join(self.dir, 'lockfile')
		lock = util.FsLock(path, True)
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
