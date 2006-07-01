# Copyright 2004-2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.mappings import ImmutableDict, LazyValDict
from pkgcore.chksum import get_handlers, get_handler
from os.path import sep as path_seperator, abspath

# goofy set of classes representating the fs objects pkgcore knows of.

__all__ = ["fsFile", "fsDir", "fsSymLink", "fsDev", "fsFifo", "isdir", "isreg", "isfs_obj"]

class fsBase(object):
	__slots__ = ["location", "real_path", "mtime", "mode", "uid", "gid"]

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
		return hash(self.location)

	def __eq__(self, other):
		if not isinstance(other, self.__class__):
			return False
		return hash(self) == hash(other)

	def __ne__(self, other):
		return not self == other


class fsFile(fsBase):

	__slots__ = fsBase.__slots__ + ["chksums"]

	def __init__(self, location, chksums=None, mtime=None, **kwds):
		if mtime is not None:
			mtime = long(mtime)
			kwds["mtime"] = mtime
		if chksums is None:
			# this can be problematic offhand if the file is modified but chksum not triggered
			chksums = LazyValDict(get_handlers().keys(), self._chksum_callback)
		elif not isinstance(chksums, ImmutableDict):
			chksums = ImmutableDict(chksums)
		kwds["chksums"] = chksums
		fsBase.__init__(self,location,**kwds)

	def __repr__(self):
		return "file:%s" % self.location

	def _chksum_callback(self, chf_type):
		return get_handler(chf_type)(self.real_path)


class fsDir(fsBase):
	__slots__ = fsBase.__slots__

	def __repr__(self):
		return "dir:%s" % self.location

	def __cmp__(self, other):
		return cmp(self.location.split(path_seperator), other.location.split(path_seperator))


class fsLink(fsBase):
	__slots__ = [x for x in fsBase.__slots__ if x != "mtime"]+ ["target"]

	def __init__(self, location, target, **kwargs):
		kwargs["target"] = target
		fsBase.__init__(self, location, **kwargs)

	def __repr__(self):
		return "symlink:%s->%s" % (self.location, self.target)


fsSymLink = fsLink


class fsDev(fsBase):
	__slots__ = fsBase.__slots__

	def __repr__(self):
		return "device:%s" % self.location


class fsFifo(fsBase):
	__slots__ = fsBase.__slots__

	def __repr__(self):
		return "fifo:%s" % self.location


isdir = lambda x: isinstance(x, fsDir)
isreg = lambda x: isinstance(x, fsFile)
isfs_obj = lambda x: isinstance(x, fsBase)
