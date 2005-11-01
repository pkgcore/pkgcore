# Copyright 2004-2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: fs.py 1911 2005-08-25 03:44:21Z ferringb $

from portage.util.mappings import ImmutableDict
from os.path import sep as path_seperator, abspath

# goofy set of classes representating the fs objects portage knows of.

__all__ = ["fsFile", "fsDir", "fsSymLink", "fsDev", "fsFifo", "isdir", "isreg", "isfs_obj"]
base_slots = ["mtime", "mode", "uid", "gid"]

class fsBase(object):
	__slots__ = ["location", "real_path"]

	def __init__(self, location, strict=True, real_path=None, **d):
			
		d["location"] = location
		if real_path is None:
			real_path = location

		if not real_path.startswith(path_seperator):
			real_path = abspath(real_path)
		
		d["real_path"] = real_path
		s = object.__setattr__
		if strict:
			for k in self.__slots__:
				s(self, k, d[k])
		else:
			for k,v in d.iteritems():
				s(self, k, v)

	def change_location(self, location):
		if not location.startswith(path_seperator):
			location = abspath(location)
			
		d = {}
		for x in self.__slots__:
			if hasattr(self, x):
				d[x] = getattr(self, x)
		del d["location"]
		return self.__class__(location, **d)

	def __setattr__(self, key, value):
		try:	
			getattr(self, key)
			raise Exception("non modifiable")
		except AttributeError:
			object.__setattr__(self, key, value)

	def __getattr__(self, attr):
		# we would only get called if it doesn't exist.
		if attr in self.__slots__:
			return None
		raise AttributeError(attr)

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
	__slots__ = tuple(base_slots + fsBase.__slots__ + ["chksums"])
	def __init__(self, location, chksums=None, mtime=None, **kwds):
		mtime = long(mtime)
		kwds["mtime"] = mtime
		if chksums is None:
			chksums = {}
		if not isinstance(chksums, ImmutableDict):
			chksums = ImmutableDict(chksums)
		kwds["chksums"] = chksums
		fsBase.__init__(self,location,**kwds)

	def __repr__(self): return "file:%s" % self.location


class fsDir(fsBase):
	__slots__ = tuple(base_slots + fsBase.__slots__)

	def __repr__(self): return "dir:%s" % self.location


class fsLink(fsBase):
	__slots__ = tuple(base_slots + fsBase.__slots__  + ["target"])

	def __init__(self, location, target, **kwargs):
		kwargs["target"] = target
		fsBase.__init__(self,location,**kwargs)

	def __repr__(self): return "symlink:%s->%s" % (self.location, self.target)


fsSymLink = fsLink


class fsDev(fsBase):
	__slots__ = fsBase.__slots__

	def __repr__(self): return "device:%s" % self.location


class fsFifo(fsBase):
	__slots__ = fsBase.__slots__
	def __repr__(self): return "fifo:%s" % self.location
	

isdir = lambda x: isinstance(x, fsDir)
isreg = lambda x: isinstance(x, fsFile)
isfs_obj = lambda x: isinstance(x, fsBase)
