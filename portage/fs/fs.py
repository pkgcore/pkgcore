# Copyright 2004-2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: fs.py 1911 2005-08-25 03:44:21Z ferringb $


# goofy set of classes representating the fs objects portage knows of.

_base_slots = ("location", "mtime", "perms", "uid", "gid")

class fsBase(object):
	__slots__=tuple(_base_slots)
	def __init__(self, location, **d):
		self.location = str(location)
		s = object.__setattr__
		for k,v in d.iteritems():
			s(self, k, v)

	def __setattr__(self, key, value):
		try:	
			getattr(self, key)
			raise Exception("non modifiable")
		except AttributeError:
			object.__setattr__(self, key, value)

	def __hash__(self):
		mylist = [];
		for key in self.__slots__:
			try:
				mylist.append(getattr(self,key))
			except AttributeError:
				pass
		mytup = tuple(mylist)
		return hash(mytup)

	def __eq__(self, other):
		if not isinstance(other, self.__class__):
			return False
		return hash(self) == hash(other)

	def __ne__(self, other):
		return not self == other


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

fsSymLink = fsLink

class fsDev(fsBase):
	__slots__ = fsBase.__slots__

	def __repr__(self): return "device:%s" % self.location

class fsFifo(fsBase):
	__slots__ = fsBase.__slots__
	def __repr__(self): return "fifo:%s" % self.location
	
