# Copyright 2004-2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: fs.py 1911 2005-08-25 03:44:21Z ferringb $


# goofy set of classes representating the fs objects portage knows of.

_base_slots = ("location", "mtime", "perms", "uid", "gid")

#try:
#	import selinux
#	_base_slots.append("selinux_label")
#
#except ImportError: 
#	pass

class fsBase(object):
	__slots__=tuple(_base_slots)
	if "selinux_label" in _base_slots:
		def __init__(self, location, mtime=None, perms=-1, uid=-1, gid=-1):
			self.location = location
#			if selinux_label:	self.selinux_label = selinux_label
			if mtime:		self.mtime = mtime
			if perms:		self.perms = perms
			if uid:			self.uid = uid
			if gid:			self.gid = gid
	else:
		def __init__(self, location, mtime=None, perms=-1, uid=-1, gid=-1):
			self.location = str(location)
			if mtime:	self.mtime = mtime
			if perms:	self.perms = perms
			if uid:		self.uid = uid
			if gid:		self.gid = gid

	def __setattr__(self, key, value):
		try:	
			getattr(self, key)
			raise Exception("non modifiable")
		except AttributeError:
			object.__setattr__(self, key, value)



class fsFile(fsBase):
	__slots__ = fsBase.__slots__ + ("md5", "size",)
	def __init__(self, location, md5=None, size=0,**kwargs):
		fsBase.__init__(self,location,**kwargs)
		self.md5  = md5
		self.size = size

	def __repr__(self): return "file:%s" % self.location

class fsDir(fsBase):
	__slots__ = fsBase.__slots__

	def __repr__(self): return "dir:%s" % self.location

class fsLink(fsBase):
	__slots__ = fsBase.__slots__ + ("target",)
	def __init__(self, location, target, **kwargs):
		fsBase.__init__(self,location,**kwargs)
		self.target = target

	def __repr__(self): return "symlink:%s->%s" % (self.location, self.target)

class fsDev(fsBase):
	__slots__ = fsBase.__slots__

	def __repr__(self): return "device:%s" % self.location


class fsFifo(fsBase):
	__slots__ = fsBase.__slots__
	def __repr__(self): return "fifo:%s" % self.location
	
