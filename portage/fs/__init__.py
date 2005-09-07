# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id:$

import os
from stat import *
from fs import *
from itertools import imap

def gen_obj(path, stat=None):
	if stat == None:
		stat = os.lstat(path)
	mode = stat.st_mode
	d = {"mtime":stat.st_mtime, "perms":S_IMODE(mode), "uid":stat.st_uid, "gid":stat.st_gid}
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
def iter_scan(path):
	sep = os.path.sep
	dirs = [path.rstrip(sep)]
	try:
		while 1:
			base = dirs.pop(0) + sep
			for x in os.listdir(base):
				path = base + x
				o = gen_obj(path)
				yield o
				if isinstance(o, fsDir):
					dirs.append(path)
	except IndexError:
		pass
