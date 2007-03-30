# Copyright: 2005-2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
interaction with the livefs: generating fs objects to represent the livefs.
"""

import os, collections
from stat import S_IMODE, S_ISDIR, S_ISREG, S_ISLNK, S_ISFIFO

from pkgcore.fs.fs import (
    fsFile, fsDir, fsSymlink, fsDev, fsFifo, get_major_minor)
from pkgcore.fs.contents import contentsSet
from pkgcore.chksum import get_handlers
from pkgcore.interfaces.data_source import local_source

from snakeoil.osutils import normpath, join as pjoin
from snakeoil.mappings import LazyValDict
from snakeoil.osutils import listdir

__all__ = ["gen_obj", "scan", "iter_scan"]


def gen_chksums(handlers, location):
    def f(key):
        return handlers[key](location)
    return LazyValDict(handlers, f)


def gen_obj(path, stat=None, chksum_handlers=None, real_location=None):

    """
    given a fs path, and an optional stat, create an appropriate fs obj.

    @param stat: stat object to reuse if available
    @param real_location: real path to the object if path is the desired
        location, rather then existant location.
    @raise KeyError: if no obj type matches the stat checks
    @return: L{pkgcore.fs.fs.fsBase} derivative
    """

    if real_location is None:
        real_location = path
    if stat is None:
        stat = os.lstat(real_location)
    if chksum_handlers is None:
        chksum_handlers = get_handlers()

    mode = stat.st_mode
    d = {"mtime":stat.st_mtime, "mode":S_IMODE(mode),
         "uid":stat.st_uid, "gid":stat.st_gid}
    if S_ISDIR(mode):
        return fsDir(path, **d)
    elif S_ISREG(mode):
        d["size"] = stat.st_size
        d["data_source"] = local_source(real_location)
        return fsFile(path, **d)
    elif S_ISLNK(mode):
        d["target"] = os.readlink(real_location)
        return fsSymlink(path, **d)
    elif S_ISFIFO(mode):
        return fsFifo(path, **d)
    else:
        major, minor = get_major_minor(stat)
        d["minor"] = minor
        d["major"] = major
        d["mode"] = mode
        return fsDev(path, **d)


# hmm. this code is roughly 25x slower then find.
# make it less slow somehow. the obj instantiation is a bit of a
# killer I'm afraid; without obj, looking at 2.3ms roughly best of 3
# 100 iterations, obj instantiation, 58ms.
# also, os.path.join is rather slow.
# in this case, we know it's always pegging one more dir on, so it's
# fine doing it this way (specially since we're relying on
# os.path.sep, not '/' :P)

def _internal_iter_scan(path, chksum_handlers):
    dirs = collections.deque([normpath(path)])
    yield gen_obj(dirs[0], chksum_handlers=chksum_handlers)
    while dirs:
        base = dirs.popleft()
        for x in listdir(base):
            path = pjoin(base, x)
            o = gen_obj(path, chksum_handlers=chksum_handlers,
                        real_location=path)
            yield o
            if isinstance(o, fsDir):
                dirs.append(path)


def _internal_offset_iter_scan(path, chksum_handlers, offset):
    offset = normpath(offset)
    path = normpath(path)
    dirs = collections.deque([path[len(offset):]])
    if dirs[0]:
        yield gen_obj(dirs[0], chksum_handlers=chksum_handlers)

    sep = os.path.sep
    while dirs:
        base = dirs.popleft()
        real_base = pjoin(offset, base.lstrip(sep))
        base = base.rstrip(sep) + sep
        for x in listdir(real_base):
            path = pjoin(base, x)
            o = gen_obj(path, chksum_handlers=chksum_handlers,
                        real_location=pjoin(real_base, x))
            yield o
            if isinstance(o, fsDir):
                dirs.append(path)


def iter_scan(path, offset=None):
    """
    Recursively scan a path.

    Does not follow symlinks pointing at dirs, just merely yields an
    obj representing said symlink

    @return: an iterator of L{pkgcore.fs.fs.fsBase} objects.

    @param path: str path of what directory to scan in the livefs
    @param offset: if not None, prefix to strip from each objects location.
        if offset is /tmp, /tmp/blah becomes /blah
    """
    chksum_handlers = get_handlers()

    if offset is None:
        return _internal_iter_scan(path, chksum_handlers)
    return _internal_offset_iter_scan(path, chksum_handlers, offset)


def scan(*a, **kw):
    """
    calls list(iter_scan(*a, **kw))
    Look at iter_scan for valid args
    """
    mutable = kw.pop("mutable", True)
    return contentsSet(iter_scan(*a, **kw), mutable=mutable)
