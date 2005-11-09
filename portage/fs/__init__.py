# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id:$

import os
from stat import *
from itertools import imap
from portage.fs.fs import *
from portage.util.fs import normpath

def gen_obj(path, stat=None, real_path=None):
	"""given a fs path, and an optional stat, return an appropriate fs obj representing that file/dir/dev/fif/link
	throws KeyError if no obj type matches the stat checks
	"""
	if real_path is None:
		real_path = path
	if stat == None:
		stat = os.lstat(real_path)
	mode = stat.st_mode
	d = {"mtime":stat.st_mtime, "mode":S_IMODE(mode), "uid":stat.st_uid, "gid":stat.st_gid, "real_path":real_path}
	if S_ISDIR(mode):
		return fsDir(path, **d)
	elif S_ISREG(mode):
		d["size"] = stat.st_size
		return fsFile(path, **d)
	elif S_ISLNK(mode):
		d["target"] = os.readlink(path)
		return fsSymLink(path, **d)
	elif S_ISFIFO(mode):
		return fsFifo(path, **d)
	elif S_ISDEV(mode):
		return fsDev(path, **d)
	else:
		raise KeyError(path)


# hmm. this code is roughly 25x slower then find.
# make it less slow somehow.  the obj instantiation is a bit of a killer I'm afraid;
# without obj, looking at 2.3ms roughly best of 3 100 iterations, obj instantiation, 58ms.
# also, os.path.join is rather slow.
# in this case, we know it's always pegging one more dir on, so it's fine doing it this way 
# (specially since we're relying on os.path.sep, not '/' :P)

def iter_scan(path, offset=None):
	"""
	generator that yield fs objects from recursively scanning a path.
	Does not follow symlinks pointing at dirs, just merely yields an obj representing said symlink
	offset is the prefix to filter from the generated objects
	"""
	sep = os.path.sep
	if offset is None:
		offset = ""
		dirs = [path.rstrip(sep)]
		yield gen_obj(dirs[0])
	else:
		offset = normpath(offset.rstrip(sep))+sep
		path = normpath(path)
		dirs = [path.rstrip(sep)[len(offset):]]
		if len(dirs[0]):
			yield gen_obj(dirs[0])

	while dirs:
		base = dirs.pop(0) + sep
		for x in os.listdir(offset + base):
			path = base + x
			o = gen_obj(path, real_path=offset+path)
			yield o
			if isinstance(o, fsDir):
				dirs.append(path)

def scan(*a, **kw):
	"""
	calls list(iter_scan(*a, **kw))
	Look at iter_scan for valid args
	"""
	
	return list(iter_scan(*a, **kw))
