# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
default fs ops.

Shouldn't be accessed directly for the most part, use L{pkgcore.plugins} to get at these ops
"""

import os, shutil, errno
from pkgcore.fs import gen_obj, contents, fs
from pkgcore.spawn import spawn
from pkgcore.const import COPY_BINARY
from pkgcore.plugins import get_plugin
from pkgcore.util.currying import pre_curry

__all__ = ["merge_contents", "unmerge_contents", "default_ensure_perms", "default_copyfile", "default_mkdir"]

def default_ensure_perms(d1,d2=None):

	"""
	enforce a fs objects attributes on the livefs (permissions, mtime, uid, gid specifically)
	
	@param d2: if not None, an fs object for what's on the livefs now
	@raise OSError: if fs object attributes can't be enforced
	@return: True on success, else an exception is thrown
	"""
	
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
		os.chmod(d1.real_location, m)
	if do_chown and (o != -1 or g != -1):
		os.lchown(d1.real_location, o, g)
	if do_mtime and t is not None:
		os.utime(d1.real_location, (t, t))
	return True


def default_mkdir(d):
	"""
	mkdir for a fsDir object
	
	@param d: L{pkgcore.fs.fs.fsDir} instance
	@raise OSError: if can't complete
	@return: true if success, else an exception is thrown
	"""
	if not d.mode:
		mode = 0777
	else:
		mode = d.mode
	os.mkdir(d.real_location, mode)
	get_plugin("fs_ops", "ensure_perms")(d)
	return True


def default_copyfile(obj):
	"""
	copy a L{fs obj<pkgcore.fs.fs.fsBase>} from it's real_path to it's stated location
	
	@param obj: L{pkgcore.fs.fs.fsBase} instance, exempting fsDir
	@raise OSError:, for non file objs, Exception (this needs to be fixed
	@return: true if success, else an exception is thrown
	"""
	
	existant = False
	ensure_perms = get_plugin("fs_ops", "ensure_perms")

	if not fs.isfs_obj(obj):
		raise TypeError("obj must be fsBase derivative")
	elif fs.isdir(obj):
		raise TypeError("obj must not be a fsDir instance")
	elif obj.real_path == obj.real_location:
		raise TypeError("obj real_path must differ from obj location")
	try:
		if fs.isdir(gen_obj(obj.real_location)):
			raise TypeError("fs_copyfile doesn't work on directories")
		existant = True
	except OSError:
		existant = False

	if fs.isreg(obj):
		if not existant:
			shutil.copyfile(obj.real_path, obj.real_location)
			ensure_perms(obj)
		else:
			shutil.copyfile(obj.real_path, obj.real_location+"#new")
			ensure_perms(obj.change_attribute(location=obj.real_location+"#new"))
			os.rename(obj.real_location+"#new", obj.real_location)
	else:
		ret = spawn([COPY_BINARY, "-R", obj.real_path, obj.real_location])
		if ret != 0:
			raise Exception("failed cp'ing %s to %s, ret %s" % (obj.real_path, obj.real_location, ret))
	return True

def offset_rewriter(offset, iterable):
	pjoin = os.path.join
	sep = os.path.sep
	for x in iterable:
		yield x.change_attribute(location=pjoin(offset, x.location.lstrip(sep)))


def merge_contents(cset, offset=None, callback=lambda obj:None):

	"""
	merge a L{pkgcore.fs.contents.contentsSet} instance to the livefs
	
	@param cset: L{pkgcore.fs.contents.contentsSet} instance
	@param offset: if not None, offset to prefix all locations with.  Think of it as target dir.
	@param callback: callable to report each entry being merged
	@raise OSError: see L{default_copyfile} and L{default_mkdir}
	@return: True, or an exception is thrown on failure (OSError, although see default_copyfile for specifics)
	"""

	from pkgcore.plugins import get_plugin

	ensure_perms = get_plugin("fs_ops", "ensure_perms")
	copyfile = get_plugin("fs_ops", "copyfile")
	mkdir = get_plugin("fs_ops", "mkdir")

	if not isinstance(cset, contents.contentsSet):
		raise TypeError("cset must be a contentsSet")

	if offset is not None:
		if os.path.exists(offset):
			if not os.path.isdir(offset):
				raise TypeError("offset must be a dir, or not exist")
		else:
			mkdir(fs.fsDir(offset, strict=False))
		iterate = pre_curry(offset_rewriter, offset.rstrip(os.path.sep))
	else:
		iterate = iter
	
	d = list(iterate(cset.iterdirs()))
	d.sort()
	for x in d:
		callback(x)

		try:
			obj = gen_obj(x.real_location)
			if not fs.isdir(obj):
				raise Exception("%s exists and needs to be a dir, but isn't" % x.location)
			ensure_perms(x, obj)
		except OSError:
			mkdir(x)
			ensure_perms(x)
	del d
	
	for x in iterate(cset.iterdirs(invert=True)):
		callback(x)
		copyfile(x)
	return True


def unmerge_contents(cset, offset=None, callback=lambda obj:None):

	"""
	unmerge a L{pkgcore.fs.contents.contentsSet} instance to the livefs
	
	@param cset: L{pkgcore.fs.contents.contentsSet} instance
	@param offset: if not None, offset to prefix all locations with.  Think of it as target dir.
	@param callback: callable to report each entry being unmerged
	@raise OSError: see L{default_copyfile} and L{default_mkdir}
	@return: True, or an exception is thrown on failure (OSError, although see default_copyfile for specifics)
	"""

	iterate = iter
	if offset is not None:
		iterate = pre_curry(offset_rewriter, offset.rstrip(os.path.sep))

	for x in iterate(cset.iterdirs(invert=True)):
		callback(x)
		try:
			os.unlink(x.location)
		except OSError, e:
			if e.errno != errno.ENOENT:
				raise
	# this is a fair sight faster then using sorted/reversed
	l = list(iterate(cset.iterdirs()))
	l.sort()
	l.reverse()
	for x in l:
		callback(x)
		try:
			os.rmdir(x.location)
		except OSError, e:
			if e.errno != errno.ENOTEMPTY and e.errno != errno.ENOENT:
				raise
	return True
