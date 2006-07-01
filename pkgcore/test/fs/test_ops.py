# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.fs import ops, fs, livefs, contents
from twisted.trial import unittest
from pkgcore.test.fs.test_util import TempDirMixin
from pkgcore.util import currying
import os, shutil
pjoin = os.path.join


class VerifyMixin(object):

	def verify(self, o, kwds, stat):
		for a, k in (("st_mtime", "mtime"), ("st_gid", "gid"), ("st_uid", "uid")):
			if k in kwds:
				self.assertEqual(getattr(stat, a), kwds[k], "testing %s" % k)
		if "mode" in kwds:
			self.assertEqual((stat.st_mode & 04777), kwds["mode"])


class TestDefaultEnsurePerms(VerifyMixin, TempDirMixin, unittest.TestCase):

	def common_bits(self, creator_func, kls):
		kwds = {"mtime":01234, "uid":os.getuid(), "gid":os.getgid(), "mode":0775}
		o = kls(pjoin(self.dir, "blah"), **kwds)
		creator_func(o.location)
		self.assertTrue(ops.default_ensure_perms(o))
		self.verify(o, kwds, os.stat(o.location))
		kwds["mode"] = 0770
		o2 = kls(pjoin(self.dir, "blah"), **kwds)
		self.assertTrue(ops.default_ensure_perms(o2))
		self.verify(o2, kwds, os.stat(o.location))
		self.assertRaises(OSError, ops.default_ensure_perms, kls(pjoin(self.dir, "asdf"), **kwds))

	def test_dir(self):
		self.common_bits(os.mkdir, fs.fsDir)
	
	def test_file(self):
		self.common_bits(lambda s:open(s, "w"), fs.fsFile)


class TestDefaultMkdir(TempDirMixin, unittest.TestCase):

	def test_it(self):
		o = fs.fsDir(pjoin(self.dir, "mkdir_test"), strict=False)
		self.assertTrue(ops.default_mkdir(o))
		u = os.umask(0)
		try:
			self.assertEqual((os.stat(o.location).st_mode & 04777), 0777 & ~u)
		finally:
			os.umask(u)
		os.rmdir(o.location)
		o = fs.fsDir(pjoin(self.dir, "mkdir_test2"), strict=False, mode=0750)
		self.assertTrue(ops.default_mkdir(o))
		self.assertEqual(os.stat(o.location).st_mode & 04777, 0750)


class TestCopyFile(VerifyMixin, TempDirMixin, unittest.TestCase):

	def test_it(self):
		src = pjoin(self.dir, "copy_test_src")
		dest = pjoin(self.dir, "copy_test_dest")
		open(src, "w").writelines("asdf\n" for x in xrange(10))
		kwds = {"mtime":10321, "uid":os.getuid(), "gid":os.getgid(), "mode":0664}
		o = fs.fsFile(dest, real_path=src, **kwds)
		self.assertTrue(ops.default_copyfile(o))
		self.assertEqual("asdf\n" * 10, open(dest, "r").read())
		self.verify(o, kwds, os.stat(o.location))
		
	def test_puke_on_dirs(self):
		self.assertRaises, ops.default_copyfile, fs.fsDir(pjoin(self.dir, "puke_dir"), strict=False)


class ContentsMixin(VerifyMixin, TempDirMixin, unittest.TestCase):

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
		pjoin = os.path.join
		s_ents = [(pjoin(base, k), entries[k]) for k in sorted(entries)]
		for k, v in s_ents:
			if v[0] == "dir":
				os.mkdir(k)
		for k,v in s_ents:
			if v[0] == "dir":
				pass
			elif v[0] == "reg":
				open(k, "w").write(os.urandom(1000))
			elif v[0] == "sym":
				os.symlink(v[1], k)
			else:
				raise Exception("generate_tree doesnt' support type %r yet: k %r" % (v,k))
	
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
		l = [k for k in self.__dict__ if k.startswith("entries") and isinstance(k, dict) and "fail" not in k]
		for e in l:
			src, dest, cset = self.generic_merge_bits(e)
			s = set(cset)
			ops.merge_contents(cset, offset=img, callback=lambda x:s.discard(s))
			self.assertFalse(s)
		
	def test_empty_overwrite(self):
		self.generic_merge_bits(self.entries_norm1)

	def test_recursive_links(self):
		self.generic_merge_bits(self.entries_rec1)

	def test_exact_overwrite(self):
		src, dest, cset = self.generic_merge_bits(self.entries_norm1)
		self.assertTrue(ops.merge_contents(cset, offset=dest))


class Test_unmerge_contents(ContentsMixin):
	
	def generic_unmerge_bits(self, entries, img="img"):
		img = self.gen_dir(img)
		self.generate_tree(img, entries)
		cset = livefs.scan(img, offset=img)
		return img, cset

	def test_callback(self):
		l = [k for k in self.__dict__ if k.startswith("entries") and isinstance(k, dict) and "fail" not in k]
		for e in l:
			img, cset = self.generic_unmerge_bits(e)
			s = set(cset)
			ops.unmerge_contents(cset, offset=img, callback=lambda x:s.discard(s))
			self.assertFalse(s)
		
	def test_empty_removal(self):
		img, cset = self.generic_unmerge_bits(self.entries_norm1)
		self.assertTrue(ops.unmerge_contents(cset, offset=os.path.join(self.dir, "dest")))

	def test_exact_removal(self):
		img, cset = self.generic_unmerge_bits(self.entries_norm1)
		self.assertTrue(ops.unmerge_contents(cset, offset=img))
		self.assertFalse(livefs.scan(img, offset=img))

	def test_lingering_file(self):
		img, cset = self.generic_unmerge_bits(self.entries_norm1)
		dirs = [k for k,v in self.entries_norm1.iteritems() if v[0] == "dir"]
		fp = os.path.join(img, dirs[0], "linger")
		open(fp, "w")
		self.assertTrue(ops.unmerge_contents(cset, offset=img))
		self.assertTrue(os.path.exists(fp))

