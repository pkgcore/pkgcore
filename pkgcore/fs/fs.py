# Copyright 2004-2005 Brian Harring <ferringb@gmail.com>
# License: GPL

"""
filesystem entry abstractions
"""

import stat
from pkgcore.util.mappings import LazyFullValLoadDict
from pkgcore.chksum import get_handlers, get_chksums
from os.path import sep as path_seperator, abspath
from pkgcore.interfaces.data_source import local_source

# goofy set of classes representating the fs objects pkgcore knows of.

__all__ = [
    "fsFile", "fsDir", "fsSymlink", "fsDev", "fsFifo", "isdir", "isreg",
    "isfs_obj"]

# following are used to generate appropriate __init__, wiped from the
# namespace at the end of the module

_fs_doc = {
    "mode":"""@keyword mode: int, the mode of this entry.  """
        """required if strict is set""",
    "mtime":"""@keyword mtime: long, the mtime of this entry.  """
        """required if strict is set""",
    "uid":"""@keyword uid: int, the uid of this entry.  """
        """required if strict is set""",
    "gid":"""@keyword gid: int, the gid of this entry.  """
        """required if strict is set""",
}

def gen_doc_additions(init, slots):
    if init.__doc__ is None:
        d = raw_init_doc.split("\n")
    else:
        d = init.__doc__.split("\n")
    init.__doc__ = "\n".join(k.lstrip() for k in d) + \
        "\n".join(_fs_doc[k] for k in _fs_doc if k in slots)


raw_init_doc = \
"""
@param location: location (real or intended) for this entry
@param strict: is this fully representative of the entry, or only partially
@raise KeyError: if strict is enabled, and not all args are passed in
"""

class fsBase(object):

    """base class, all extensions must derive from this class"""
    __slots__ = ("location", "_real_location", "mtime", "mode", "uid", "gid")
    __attrs__ = __slots__

    def __init__(self, location, real_location=None, strict=True, **d):

        d["location"] = location

        if real_location is not None:
            if not real_location.startswith(path_seperator):
                real_location = abspath(real_location)
        d["_real_location"] = real_location
        s = object.__setattr__
        if strict:
            for k in self.__attrs__:
                s(self, k, d[k])
        else:
            for k, v in d.iteritems():
                s(self, k, v)
    gen_doc_additions(__init__, __attrs__)

    def change_attributes(self, **kwds):
        d = dict((x, getattr(self, x))
                 for x in self.__attrs__ if hasattr(self, x))
        d.update(kwds)
        # split location out
        location = d.pop("location")
        if not location.startswith(path_seperator):
            location = abspath(location)
        d["strict"] = False
        return self.__class__(location, **d)

    def __setattr__(self, key, value):
        try:
            getattr(self, key)
            raise Exception("non modifiable")
        except AttributeError:
            object.__setattr__(self, key, value)

    def __getattr__(self, attr):
        # we would only get called if it doesn't exist.
        if attr in self.__attrs__:
            return None
        raise AttributeError(attr)

    def __hash__(self):
        return hash(self.location)

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return self.location == other.location

    def __ne__(self, other):
        return not self == other

    @property
    def real_location(self):
        if self._real_location is not None:
            return self._real_location
        return self.location


known_handlers = tuple(get_handlers())

class fsFile(fsBase):

    """file class"""

    __slots__ = ("chksums", "data_source")
    __attrs__ = fsBase.__attrs__ + __slots__

    def __init__(self, location, chksums=None, real_location=None, **kwds):
        """
        @param chksums: dict of checksums, key chksum_type: val hash val.
            See L{pkgcore.chksum}.
        """
        if "mtime" in kwds:
            kwds["mtime"] = long(kwds["mtime"])
        if real_location is not None:
            if "data_source" in kwds:
                raise TypeError(
                    "%s: real_location and data_source are mutually exclusive "
                    "options" % self.__class__)
            kwds["data_source"] = local_source(real_location)
        else:
            kwds.setdefault("data_source", None)
        if chksums is None:
            # this can be problematic offhand if the file is modified
            # but chksum not triggered
            chksums = LazyFullValLoadDict(known_handlers, self._chksum_callback)
        kwds["chksums"] = chksums
        fsBase.__init__(self, location, **kwds)
    gen_doc_additions(__init__, __slots__)

    def __repr__(self):
        return "file:%s" % self.location

    def _chksum_callback(self, chfs):
        return zip(chfs, get_chksums(self.data, *chfs))

    @property
    def data(self):
        o = self.data_source
        if o is not None:
            return o
        return local_source(self.real_location)


class fsDir(fsBase):

    """dir class"""

    __slots__ = ()

    def __repr__(self):
        return "dir:%s" % self.location

    def __cmp__(self, other):
        return cmp(
            self.location.split(path_seperator),
            other.location.split(path_seperator))


class fsLink(fsBase):

    """symlink class"""

    __slots__ = ("target",)
    __attrs__ = fsBase.__attrs__ + __slots__

    def __init__(self, location, target, **kwargs):
        """
        @param target: string, filepath of the symlinks target
        """
        kwargs["target"] = target
        fsBase.__init__(self, location, **kwargs)
    gen_doc_additions(__init__, __slots__)

    def change_attributes(self, **kwds):
        d = dict((x, getattr(self, x))
                 for x in self.__slots__ if hasattr(self, x))
        d.update(kwds)
        # split location out
        location = d.pop("location")
        if not location.startswith(path_seperator):
            location = abspath(location)
        target = d.pop("target")
        d["strict"] = False
        return self.__class__(location, target, **d)

    def __repr__(self):
        return "symlink:%s->%s" % (self.location, self.target)


fsSymlink = fsLink


class fsDev(fsBase):

    """dev class (char/block objects)"""

    __slots__ = ("major", "minor")
    __attrs__ = fsBase.__attrs__ + __slots__

    def __init__(self, path, major=-1, minor=-1, **kwds):
        if kwds.get("strict", True):
            if major == -1 or minor == -1:
                raise TypeError(
                    "major/minor must be specified and positive ints")
            if not stat.S_IFMT(kwds["mode"]):
                raise TypeError(
                    "mode %o: must specify the device type (got %o)" % (
                        kwds["mode"], stat.S_IFMT(kwds["mode"])))
            kwds["major"] = major
            kwds["minor"] = minor
        fsBase.__init__(self, path, **kwds)

    def __repr__(self):
        return "device:%s" % self.location


def get_major_minor(stat_inst):
    """get major/minor from a stat instance
    @return: major,minor tuple of ints
    """
    return ( stat_inst.st_rdev >> 8 ) & 0xff, stat_inst.st_rdev & 0xff


class fsFifo(fsBase):

    """fifo class (socket objects)"""

    __slots__ = ()

    def __repr__(self):
        return "fifo:%s" % self.location


isdir    = lambda x: isinstance(x, fsDir)
isreg    = lambda x: isinstance(x, fsFile)
issym    = lambda x: isinstance(x, fsSymlink)
isfifo   = lambda x: isinstance(x, fsFifo)
isdev    = lambda x: isinstance(x, fsDev)
isfs_obj = lambda x: isinstance(x, fsBase)

del raw_init_doc, gen_doc_additions, _fs_doc
