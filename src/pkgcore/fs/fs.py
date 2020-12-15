"""
filesystem entry abstractions
"""

import fnmatch
import stat
from os.path import abspath, basename, dirname, realpath
from os.path import sep as path_seperator

from snakeoil import klass
from snakeoil.chksum import get_chksums, get_handlers
from snakeoil.compatibility import cmp
from snakeoil.currying import post_curry, pretty_docs
from snakeoil.data_source import local_source
from snakeoil.mappings import LazyFullValLoadDict
from snakeoil.osutils import normpath, pjoin

# goofy set of classes representating the fs objects pkgcore knows of.

__all__ = [
    "fsFile", "fsDir", "fsSymlink", "fsDev", "fsFifo"]
__all__.extend(
    f"is{x}" for x in ("dir", "reg", "sym", "fifo", "dev", "fs_obj"))

# following are used to generate appropriate __init__, wiped from the
# namespace at the end of the module

_fs_doc = {
    "mode":""":keyword mode: int, the mode of this entry.  """
        """required if strict is set""",
    "mtime":""":keyword mtime: long, the mtime of this entry.  """
        """required if strict is set""",
    "uid":""":keyword uid: int, the uid of this entry.  """
        """required if strict is set""",
    "gid":""":keyword gid: int, the gid of this entry.  """
        """required if strict is set""",
}

def gen_doc_additions(init, slots):
    if init.__doc__ is None:
        d = \
"""
:param location: location (real or intended) for this entry
:param strict: is this fully representative of the entry, or only partially
:raise KeyError: if strict is enabled, and not all args are passed in
""".split("\n")
    else:
        d = init.__doc__.split("\n")
    init.__doc__ = "\n".join(k.lstrip() for k in d) + \
        "\n".join(_fs_doc[k] for k in _fs_doc if k in slots)


class fsBase:

    """base class, all extensions must derive from this class"""
    __slots__ = ("location", "mtime", "mode", "uid", "gid")
    __attrs__ = __slots__
    __default_attrs__ = {}

    locals().update((x.replace("is", "is_"), False) for x in
        __all__ if x.startswith("is") and x.islower() and not
            x.endswith("fs_obj"))

    klass.inject_richcmp_methods_from_cmp(locals())
    klass.inject_immutable_instance(locals())

    def __init__(self, location, strict=True, **d):

        d["location"] = normpath(location)

        s = object.__setattr__
        if strict:
            for k in self.__attrs__:
                s(self, k, d[k])
        else:
            for k, v in d.items():
                s(self, k, v)
    gen_doc_additions(__init__, __attrs__)

    def change_attributes(self, **kwds):
        d = {x: getattr(self, x)
             for x in self.__attrs__ if hasattr(self, x)}
        d.update(kwds)
        # split location out
        location = d.pop("location")
        if not location.startswith(path_seperator):
            location = abspath(location)
        d["strict"] = False
        return self.__class__(location, **d)

    def __getattr__(self, attr):
        # we would only get called if it doesn't exist.
        if attr not in self.__attrs__:
            raise AttributeError(self, attr)
        obj = self.__default_attrs__.get(attr)
        if not callable(obj):
            return obj
        return obj(self)

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

        :keyword cache: Either None (no cache), or a data object of path->
          resolved.  Currently unused, but left in for forwards compatibility
        """
        new_path = realpath(self.location)
        if new_path == self.location:
            return self
        return self.change_attributes(location=new_path)

    @property
    def basename(self):
        return basename(self.location)

    @property
    def dirname(self):
        return dirname(self.location)

    def fnmatch(self, pattern):
        return fnmatch.fnmatch(self.location, pattern)

    def __cmp__(self, other):
        return cmp(self.location, other.location)

    def __str__(self):
        return self.location


class _LazyChksums(LazyFullValLoadDict):
    __slots__ = ()


class fsFile(fsBase):

    """file class"""

    __slots__ = ("chksums", "data", "dev", "inode")
    __attrs__ = fsBase.__attrs__ + __slots__
    __default_attrs__ = {"mtime":0, 'dev':None, 'inode':None}

    is_reg = True

    def __init__(self, location, chksums=None, data=None, **kwds):
        """
        :param chksums: dict of checksums, key chksum_type: val hash val.
            See :obj:`snakeoil.chksum`.
        """
        assert 'data_source' not in kwds
        if data is None:
            data = local_source(location)
        kwds["data"] = data

        if chksums is None:
            # this can be problematic offhand if the file is modified
            # but chksum not triggered
            chf_types = kwds.pop("chf_types", None)
            if chf_types is None:
                chf_types = tuple(get_handlers())
            chksums = _LazyChksums(chf_types, self._chksum_callback)
        kwds["chksums"] = chksums
        fsBase.__init__(self, location, **kwds)
    gen_doc_additions(__init__, __slots__)

    def __repr__(self):
        return f"file:{self.location}"

    data_source = klass.alias_attr("data")

    def _chksum_callback(self, chfs):
        return list(zip(chfs, get_chksums(self.data, *chfs)))

    def change_attributes(self, **kwds):
        if 'data' in kwds and ('chksums' not in kwds and
            isinstance(self.chksums, _LazyChksums)):
            kwds['chksums'] = None
        return fsBase.change_attributes(self, **kwds)

    def _can_be_hardlinked(self, other):
        if not other.is_reg:
            return False

        if None in (self.inode, self.dev):
            return False

        for attr in ('dev', 'inode', 'uid', 'gid', 'mode', 'mtime'):
            if getattr(self, attr) != getattr(other, attr):
                return False
        return True


class fsDir(fsBase):

    """dir class"""

    __slots__ = ()
    is_dir = True

    def __repr__(self):
        return f"dir:{self.location}"


class fsLink(fsBase):

    """symlink class"""

    __slots__ = ("target",)
    __attrs__ = fsBase.__attrs__ + __slots__
    is_sym = True

    def __init__(self, location, target, **kwargs):
        """
        :param target: string, filepath of the symlinks target
        """
        kwargs["target"] = target
        fsBase.__init__(self, location, **kwargs)
    gen_doc_additions(__init__, __slots__)

    def change_attributes(self, **kwds):
        d = {x: getattr(self, x)
             for x in self.__attrs__ if hasattr(self, x)}
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

    def __cmp__(self, other):
        c = cmp(self.location, other.location)
        if c:
            return c
        if isinstance(other, self.__class__):
            return cmp(self.target, other.target)
        return 0

    def __str__(self):
        return f'{self.location} -> {self.target}'

    def __repr__(self):
        return f"symlink:{self.location}->{self.target}"


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
        return f"device:{self.location}"


def get_major_minor(stat_inst):
    """get major/minor from a stat instance
    :return: major,minor tuple of ints
    """
    return ( stat_inst.st_rdev >> 8 ) & 0xff, stat_inst.st_rdev & 0xff


class fsFifo(fsBase):

    """fifo class (socket objects)"""

    __slots__ = ()
    is_fifo = True

    def __repr__(self):
        return f"fifo:{self.location}"

def mk_check(name):
    return pretty_docs(post_curry(getattr, 'is_' + name, False),
        extradocs=("return True if obj is an instance of :obj:`%s`, else False" % name),
        name=("is" +name)
        )

isdir    = mk_check('dir')
isreg    = mk_check('reg')
issym    = mk_check('sym')
isfifo   = mk_check('fifo')
isdev    = mk_check('dev')
isfs_obj = pretty_docs(post_curry(isinstance, fsBase), name='isfs_obj',
    extradocs='return True if obj is an fsBase derived object')

del gen_doc_additions, mk_check
