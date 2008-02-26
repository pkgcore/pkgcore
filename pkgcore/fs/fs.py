# Copyright 2004-2006 Brian Harring <ferringb@gmail.com>
# License: GPL

"""
filesystem entry abstractions
"""

import stat
from pkgcore.chksum import get_handlers, get_chksums
from os.path import sep as path_seperator, realpath, abspath
from pkgcore.interfaces.data_source import local_source
from snakeoil.mappings import LazyFullValLoadDict
from snakeoil.osutils import normpath, pjoin

# goofy set of classes representating the fs objects pkgcore knows of.

__all__ = [
    "fsFile", "fsDir", "fsSymlink", "fsDev", "fsFifo"]
__all__.extend("is%s" % x for x in ("dir", "reg", "sym", "fifo", "dev",
    "fs_obj"))

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
    __slots__ = ("location", "mtime", "mode", "uid", "gid")
    __attrs__ = __slots__
    __default_attrs__ = {}

    locals().update((x.replace("is", "is_"), False) for x in
        __all__ if x.startswith("is") and x.islower() and not
            x.endswith("fs_obj"))

    def __init__(self, location, strict=True, **d):

        d["location"] = normpath(location)

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
        raise AttributeError(key)

    def __getattr__(self, attr):
        # we would only get called if it doesn't exist.
        if attr in self.__attrs__:
            return self.__default_attrs__.get(attr)
        raise AttributeError(attr)

    def __hash__(self):
        return hash(self.location)

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return self.location == other.location

    def __ne__(self, other):
        return not self == other

    def realpath(self, cache=None):
        """calculate the abspath/canonicalized path for this entry, returning
        a new instance if the path differs.

        @keyword cache: Either None (no cache), or a data object of path->
          resolved.  Currently unused, but left in for forwards compatibility
        """
        new_path = realpath(self.location)
        if new_path == self.location:
            return self
        return self.change_attributes(location=new_path)


known_handlers = tuple(get_handlers())

class fsFile(fsBase):

    """file class"""

    __slots__ = ("chksums", "data_source")
    __attrs__ = fsBase.__attrs__ + __slots__
    __default_attrs__ = {"mtime":0l}

    is_reg = True

    def __init__(self, location, chksums=None, data_source=None, **kwds):
        """
        @param chksums: dict of checksums, key chksum_type: val hash val.
            See L{pkgcore.chksum}.
        """
        if "mtime" in kwds:
            kwds["mtime"] = long(kwds["mtime"])
        if data_source is None:
            data_source = local_source(location)
        kwds["data_source"] = data_source

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
        return self.data_source


class fsDir(fsBase):

    """dir class"""

    __slots__ = ()
    is_dir = True

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
    is_sym = True

    def __init__(self, location, target, **kwargs):
        """
        @param target: string, filepath of the symlinks target
        """
        kwargs["target"] = target
        fsBase.__init__(self, location, **kwargs)
    gen_doc_additions(__init__, __slots__)

    def change_attributes(self, **kwds):
        d = dict((x, getattr(self, x))
                 for x in self.__attrs__ if hasattr(self, x))
        d.update(kwds)
        # split location out
        location = d.pop("location")
        if not location.startswith(path_seperator):
            location = abspath(location)
        target = d.pop("target")
        d["strict"] = False
        return self.__class__(location, target, **d)

    @property
    def resolved_target(self):
        if self.target.startswith("/"):
            return self.target
        return normpath(pjoin(self.location, '../', self.target))

    def __repr__(self):
        return "symlink:%s->%s" % (self.location, self.target)


fsSymlink = fsLink


class fsDev(fsBase):

    """dev class (char/block objects)"""

    __slots__ = ("major", "minor")
    __attrs__ = fsBase.__attrs__ + __slots__
    __default_attrs__ = {"major":-1, "minor":-1}
    is_dev = True

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
        else:
            if major != -1:
                major = int(major)
                if major < 0:
                    raise TypeError(
                       "major/minor must be specified and positive ints")
                kwds["major"] = major

            if minor != -1:
                minor = int(minor)
                if minor < 0:
                    raise TypeError(
                       "major/minor must be specified and positive ints")
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
    is_fifo = True

    def __repr__(self):
        return "fifo:%s" % self.location

def mk_check(target, name):
    def f(obj):
        return isinstance(obj, target)
    f.__name__ = name
    f.__doc__ = "return True if obj is an instance of L{%s}, else False" % target.__name__
    return f

isdir    = mk_check(fsDir, 'isdir')
isreg    = mk_check(fsFile, 'isreg')
issym    = mk_check(fsSymlink, 'issym')
isfifo   = mk_check(fsFifo, 'isfifo')
isdev    = mk_check(fsDev, 'isdev')
isfs_obj = mk_check(fsBase, 'isfs_obj')

del raw_init_doc, gen_doc_additions, _fs_doc, mk_check
