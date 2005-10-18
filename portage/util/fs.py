# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: fs.py 2140 2005-10-18 08:01:45Z ferringb $
cvs_id_string="$Id: fs.py 2140 2005-10-18 08:01:45Z ferringb $"[5:-2]

import os

def ensure_dirs(path, gid=-1, uid=-1, mode=0777):
	"""ensure dirs exist, creating as needed with (optional) gid, uid, and mode"""

	try:
		st = os.stat(path)
	except OSError:
		base = os.path.sep
		try:
			um = os.umask(0)
			for dir in os.path.abspath(path).split(os.path.sep):
				base = os.path.join(base,dir)
				if not os.path.exists(base):
					try:
						os.mkdir(base, mode)
						if gid != -1 or uid != -1:
							os.chown(base, uid, gid)
					except OSError:
						return False
		finally:
			os.umask(um)
		return True
	try:
		um = os.umask(0)
		try:
			if (gid != -1 and gid != st.st_gid) or (uid != -1 and uid != st.st_uid):
				os.chown(path, uid, gid)
			if mode != (st.st_mode & 04777):
				os.chmod(path, mode)
		except OSError:
			return False
	finally:
		os.umask(um)
	return True


# XXX throw this out.
try:
	#XXX: This should get renamed to bsd_chflags, I think.
	import chflags
	bsd_chflags = chflags
except SystemExit, e:
	raise
except:
	# XXX: This should get renamed to bsd_chflags, I think.
	bsd_chflags = None


def abssymlink(symlink):
	"""
	This reads symlinks, resolving the relative symlinks, and returning the absolute.
	"""
	import os.path
	mylink=os.readlink(symlink)
	if mylink[0] != '/':
		mydir=os.path.dirname(symlink)
		mylink=mydir+"/"+mylink
	return os.path.normpath(mylink)


def normpath(mypath):
	newpath = os.path.normpath(mypath)
	if len(newpath) > 1:
		if newpath[:2] == "//":
			return newpath[1:]
	return newpath
