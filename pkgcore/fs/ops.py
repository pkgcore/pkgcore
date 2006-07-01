# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os, shutil, errno
from itertools import ifilterfalse
from pkgcore.fs import gen_obj, contents, fs
from pkgcore.spawn import spawn
from pkgcore.const import COPY_BINARY
from pkgcore.plugins import get_plugin

__all__ = ["merge_contents"]

def default_ensure_perms(d1,d2=None):
	m, o, g, t = d1.mode, d1.uid, d1.gid, d1.mtime
	if o is None:
		o = -1
	if g is None:
		g = -1
	if d2 is None:
		do_mode, do_chown, do_mtime = True, True, True
	else:

		do_mode = False
		try:
			do_mode = (m is not None and m != d2.mode)
		except AttributeError:
			# yes.  this _is_ stupid.  vdb's don't always store all attributes
			do_mode = False

		do_chown = False
		try:
			do_chown = (o != d2.uid or g != d2.gid)
		except AttributeError:
			do_chown = True

		try:
			do_mtime = (t != d2.mtime)
		except AttributeError:
			do_mtime = True

	if do_mode and m is not None:
		os.chmod(d1.location, m)
	if do_chown and (o != -1 or g != -1):
		os.lchown(d1.location, o, g)
	if do_mtime and t is not None:
		os.utime(d1.location, (t, t))
	return True


def default_mkdir(d):
	if not d.mode:
		mode = 0777
	else:
		mode = d.mode
	os.mkdir(d.location, mode)
	get_plugin("fs_ops", "ensure_perms")(d)
	return True


def default_copyfile(obj):
	existant = False
	ensure_perms = get_plugin("fs_ops", "ensure_perms")

	if not fs.isfs_obj(obj):
		raise TypeError("obj must be fsBase derivative")
	elif fs.isdir(obj):
		raise TypeError("obj must not be a fsDir instance")
	elif obj.real_path == obj.location:
		raise TypeError("obj real_path must differ from obj location")
	try:
		if fs.isdir(gen_obj(obj.location)):
			raise TypeError("fs_copyfile doesn't work on directories")
		existant = True
	except OSError:
		existant = False

	if fs.isreg(obj):
		if not existant:
			shutil.copyfile(obj.real_path, obj.location)
			ensure_perms(obj)
		else:
			shutil.copyfile(obj.real_path, obj.location+"#new")
			ensure_perms(obj.change_location(obj.location+"#new"))
			os.rename(obj.location+"#new", obj.location)
	else:
		ret = spawn([COPY_BINARY, "-R", obj.real_path, obj.location])
		if ret != 0:
			raise Exception("failed cp'ing %s to %s, ret %s" % (obj.real_path, obj.location, ret))
	return True


def merge_contents(cset, offset=None):
	from pkgcore.plugins import get_plugin

	ensure_perms = get_plugin("fs_ops", "ensure_perms")
	copyfile = get_plugin("fs_ops", "copyfile")
	mkdir = get_plugin("fs_ops", "mkdir")

	if os.path.exists(offset) and not os.path.isdir(offset):
		raise TypeError("offset must be a dir, or not exist")
	if not isinstance(cset, contents.contentsSet):
		raise TypeError("cset must be a contentsSet")
	if not os.path.exists(offset):
		mkdir(fs.fsDir(offset, strict=False))

	for x in sorted(cset.iterdirs()):
		# XXX temporary until this is chunked for output
		print "installing",x

		try:
			obj = gen_obj(x.location)
			if not fs.isdir(obj):
				raise Exception("%s exists and needs to be a dir, but isn't" % x.location)
			ensure_perms(x, obj)
		except OSError:
			mkdir(x)

	for x in ifilterfalse(fs.isdir, cset):
		# XXX temporary until this is chunked for output
		print "installing",x
		copyfile(x)


def unmerge_contents(cset):
	for x in ifilterfalse(lambda x: isinstance(x, fs.fsDir), cset):
		# XXX temporary until this is chunked for output
		print "removing",x
		try:
			os.unlink(x.location)
		except OSError, e:
			if e.errno != errno.ENOENT:
				raise
	# this is a fair sight faster then using sorted/reversed
	l = cset.dirs()
	l.sort()
	l.reverse()
	for x in l:
		# XXX temporary until this is chunked for output
		print "removing",x
		try:
			os.rmdir(x.location)
		except OSError, e:
			if e.errno != errno.ENOTEMPTY and e.errno != errno.ENOENT:
				raise

