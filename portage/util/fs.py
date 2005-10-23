# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: fs.py 2156 2005-10-23 23:48:48Z ferringb $
cvs_id_string="$Id: fs.py 2156 2005-10-23 23:48:48Z ferringb $"[5:-2]

import os
import fcntl

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
		# final one, since g+s can occur.
		os.chmod(path, mode)
		if uid != -1 or gid != -1:
			os.chown(path, uid, gid)
		return True
	try:
		um = os.umask(0)
		try:
			if (gid != -1 and gid != st.st_gid) or (uid != -1 and uid != st.st_uid):
				os.chown(path, uid, gid)
			if mode != (st.st_mode & 07777):
				os.chmod(path, mode)
		except OSError:
			return False
	finally:
		os.umask(um)
	return True


def abssymlink(symlink):
	"""
	This reads symlinks, resolving the relative symlinks, and returning the absolute.
	"""
	mylink=os.readlink(symlink)
	if mylink[0] != '/':
		mydir=os.path.dirname(symlink)
		mylink=mydir+"/"+mylink
	return os.path.normpath(mylink)


def normpath(mypath):
	newpath = os.path.normpath(mypath)
	if newpath.startswith('//'):
		return newpath[1:]
	return newpath


class LockException(Exception):
	"""Base lock exception class"""
	def __init__(self, path, reason):
		self.path, self.reason = path, reason
		
class NonExistant(LockException):
	"""Missing file/dir exception"""
	def __init__(self, path, reason=None):
		LockException.__init__(self, path, reason)
	def __str__(self):
		return "Lock action for '%s' failed due to not being a valid dir/file %s" % (self.path, self.reason)

class GenericFailed(LockException):
	"""the fallback lock exception class- covers perms, IOError's, and general whackyness"""
	def __str__(self):
		return "Lock action for '%s' failed due to '%s'" % (self.path, self.reason)


# should the fd be left open indefinitely?
# IMO, it shouldn't, but opening/closing everytime around is expensive

class FsLock(object):
	__slots__ = ["path", "fd", "create"]
	def __init__(self, path, create=False):
		"""path specifies the fs path for the lock
		create controls whether the file will be create if the file doesn't exist
		if create is true, the base dir must exist, and it will create a file
		
		If you want a directory yourself, create it.
		"""
		self.path = path
		self.fd = None
		self.create = create
		if not create:
			if not os.path.exists(path):
				raise NonExistant(path)

	def _acquire_fd(self):
		if self.create:
			try:	self.fd = os.open(self.path, os.R_OK|os.O_CREAT)
			except OSError, oe:
				raise GenericFailed(self.path, oe)
		else:
			try:	self.fd = os.open(self.path, os.R_OK)
			except OSError, oe:	raise NonExistant(self.path, oe)
	
	def _enact_change(self, flags, blocking):
		if self.fd == None:
			self._acquire_fd()
		# we do it this way, due to the fact try/except is a bit of a hit
		if not blocking:
			try:	fcntl.flock(self.fd, flags|fcntl.LOCK_NB)
			except IOError, ie:
				if ie.errno == 11:
					return False
				raise GenericFailed(self.path, ie)
		else:
			fcntl.flock(self.fd, flags)
		return True

	def acquire_write_lock(self, blocking=True):
		"""Acquire an exclusive lock
		Returns True if lock is acquired, False if not.
		Note if you have a read lock, it implicitly upgrades atomically"""
		return self._enact_change(fcntl.LOCK_EX, blocking)

	def acquire_read_lock(self, blocking=True):
		"""Acquire a shared lock
		Returns True if lock is acquired, False if not.
		Note, if you have a write_lock already, it'll implicitly downgrade atomically"""
		return self._enact_change(fcntl.LOCK_SH, blocking)
	
	def release_write_lock(self):
		"""Release an exclusive lock if held"""
		self._enact_change(fcntl.LOCK_UN, False)
		
	def release_read_lock(self):
		self._enact_change(fcntl.LOCK_UN, False)

	def __del__(self):
		# alright, it's 5:45am, yes this is weird code.
		try:
			if self.fd != None:
				self.release_read_lock()
		finally:
			if self.fd != None:
				os.close(self.fd)

