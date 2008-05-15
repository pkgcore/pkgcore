# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
default fs ops.

Shouldn't be accessed directly for the most part, use
L{pkgcore.plugins} to get at these ops.
"""

import os, errno

from pkgcore.fs import contents, fs
from pkgcore.fs.livefs import gen_obj
from pkgcore.spawn import spawn
from pkgcore.const import COPY_BINARY
from pkgcore.plugin import get_plugin

from snakeoil.currying import partial
from snakeoil.osutils import ensure_dirs, pjoin, normpath

__all__ = [
    "merge_contents", "unmerge_contents", "default_ensure_perms",
    "default_copyfile", "default_mkdir"]

def default_ensure_perms(d1, d2=None):

    """Enforce a fs objects attributes on the livefs.

    Attributes enforced are permissions, mtime, uid, gid.

    @param d2: if not None, an fs object for what's on the livefs now
    @raise OSError: if fs object attributes can't be enforced
    @return: True on success, else an exception is thrown
    """

    m, o, g, t = d1.mode, d1.uid, d1.gid, d1.mtime
    if o is None:
        o = -1
    if g is None:
        g = -1
    if d2 is None:
        do_mode, do_chown, do_mtime = True, True, True
    else:

        do_mode = False
        try:
            if fs.isdir(d1) and fs.isdir(d2):
                # if it's preexisting, keep it's perms.
                do_mode = False
            else:
                do_mode = (m is not None and m != d2.mode)
        except AttributeError:
            # yes.  this _is_ stupid.  vdb's don't always store all attributes
            do_mode = False

        do_chown = False
        try:
            do_chown = (o != d2.uid or g != d2.gid)
        except AttributeError:
            do_chown = True

        try:
            do_mtime = (t != d2.mtime)
        except AttributeError:
            do_mtime = True

    if do_chown and (o != -1 or g != -1):
        os.lchown(d1.location, o, g)
    if do_mode and m is not None:
        os.chmod(d1.location, m)
    if do_mtime and t is not None:
        os.utime(d1.location, (t, t))
    return True


def default_mkdir(d):
    """
    mkdir for a fsDir object

    @param d: L{pkgcore.fs.fs.fsDir} instance
    @raise OSError: if can't complete
    @return: true if success, else an exception is thrown
    """
    if not d.mode:
        mode = 0777
    else:
        mode = d.mode
    os.mkdir(d.location, mode)
    get_plugin("fs_ops.ensure_perms")(d)
    return True

# minor hack.

class FailedCopy(TypeError):

    def __init__(self, obj, msg):
        self.obj = obj
        self.msg = msg

    def __str__(self):
        return "failed copying %s:" % (self.obj, self.msg)


class CannotOverwrite(FailedCopy):
    def __init__(self, obj, existing):
        self.obj, self.existing = obj, existing

    def __str__(self):
        return "cannot write %s due to %s existing" % (
            self.obj, self.existing)


def default_copyfile(obj, mkdirs=False):
    """
    copy a L{fs obj<pkgcore.fs.fs.fsBase>} to it's stated location.

    @param obj: L{pkgcore.fs.fs.fsBase} instance, exempting fsDir
    @raise OSError:, for non file objs, Exception (this needs to be fixed
    @return: true if success, else an exception is thrown
    """

    existant = False
    ensure_perms = get_plugin("fs_ops.ensure_perms")
    if not fs.isfs_obj(obj):
        raise TypeError("obj must be fsBase derivative: %r" % obj)
    elif fs.isdir(obj):
        raise TypeError("obj must not be a fsDir instance: %r" % obj)

    try:
        existing = gen_obj(obj.location)
        if fs.isdir(existing):
            raise CannotOverwrite(obj, existing)
        existant = True
    except OSError, oe:
        # verify the parent dir is there at least
        basefp = os.path.dirname(obj.location)
        if basefp.strip(os.path.sep) and not os.path.exists(basefp):
            if mkdirs:
                if not ensure_dirs(basefp, mode=0750, minimal=True):
                    raise FailedCopy(obj, str(oe))
            else:
                raise
        existant = False

    if not existant:
        fp = obj.location
    else:
        fp = existant_fp = obj.location + "#new"

    if fs.isreg(obj):
        src_f = obj.data.get_fileobj()
        new_f = open(fp, "wb", 32768)
        d = src_f.read(32768)
        while d:
            new_f.write(d)
            d = src_f.read(32768)
        new_f.close()
        del src_f
    elif fs.issym(obj):
        os.symlink(obj.target, fp)
    elif fs.isfifo(obj):
        os.mkfifo(fp)
    elif fs.isdev(obj):
        dev = os.makedev(obj.major, obj.minor)
        os.mknod(fp, obj.mode, dev)
    else:
        ret = spawn([COPY_BINARY, "-Rp", obj.location, fp])
        if ret != 0:
            raise FailedCopy(obj, "got %i from %s -Rp" % ret)
    if not fs.issym(obj):
        ensure_perms(obj.change_attributes(location=fp))

    if existant:
        os.rename(existant_fp, obj.location)
    return True


def change_offset_rewriter(orig_offset, new_offset, iterable):
    offset_len = len(orig_offset.rstrip(os.path.sep))
    # localize it.
    npf = normpath
    path_sep = os.path.sep
    for x in iterable:
        # slip in the '/' default to force it to still generate a
        # full path still
        yield x.change_attributes(
            location=npf(pjoin(new_offset, x.location[offset_len:].lstrip(path_sep))))

offset_rewriter = partial(change_offset_rewriter, '/')


def merge_contents(cset, offset=None, callback=lambda obj:None):

    """
    merge a L{pkgcore.fs.contents.contentsSet} instance to the livefs

    @param cset: L{pkgcore.fs.contents.contentsSet} instance
    @param offset: if not None, offset to prefix all locations with.
        Think of it as target dir.
    @param callback: callable to report each entry being merged
    @raise OSError: see L{default_copyfile} and L{default_mkdir}
    @return: True, or an exception is thrown on failure
        (OSError, although see default_copyfile for specifics).
    """

    ensure_perms = get_plugin("fs_ops.ensure_perms")
    copyfile = get_plugin("fs_ops.copyfile")
    mkdir = get_plugin("fs_ops.mkdir")

    if not isinstance(cset, contents.contentsSet):
        raise TypeError("cset must be a contentsSet, got %r" % (cset,))

    if offset is not None:
        if os.path.exists(offset):
            if not os.path.isdir(offset):
                raise TypeError("offset must be a dir, or not exist: %s" % offset)
        else:
            mkdir(fs.fsDir(offset, strict=False))
        iterate = partial(offset_rewriter, offset.rstrip(os.path.sep))
    else:
        iterate = iter

    d = list(iterate(cset.iterdirs()))
    d.sort()
    for x in d:
        callback(x)

        try:
            # we pass in the stat ourselves, using stat instead of
            # lstat gen_obj uses internally; this is the equivalent of
            # "deference that link"
            obj = gen_obj(x.location,  stat=os.stat(x.location))
            if not fs.isdir(obj):
                raise Exception(
                    "%s exists and needs to be a dir, but is a %s" %
                        (x.location, obj))
            ensure_perms(x, obj)
        except OSError, oe:
            if oe.errno != errno.ENOENT:
                raise
            try:
                # we do this form to catch dangling symlinks
                mkdir(x)
            except OSError, oe:
                if oe.errno != errno.EEXIST:
                    raise
                os.unlink(x.location)
                mkdir(x)
            ensure_perms(x)
    del d

    # might look odd, but what this does is minimize the try/except cost
    # to one time, assuming everything behaves, rather then per item.
    i = iterate(cset.iterdirs(invert=True))
    while True:
        try:
            for x in i:
                callback(x)
                copyfile(x, mkdirs=True)
            break
        except CannotOverwrite, cf:
            if not fs.issym(x):
                raise

            # by this time, all directories should've been merged.
            # thus we can check the target
            try:
                if not fs.isdir(gen_obj(pjoin(x.location, x.target))):
                    raise
            except OSError:
                raise cf
    return True


def unmerge_contents(cset, offset=None, callback=lambda obj:None):

    """
    unmerge a L{pkgcore.fs.contents.contentsSet} instance to the livefs

    @param cset: L{pkgcore.fs.contents.contentsSet} instance
    @param offset: if not None, offset to prefix all locations with.
        Think of it as target dir.
    @param callback: callable to report each entry being unmerged
    @raise OSError: see L{default_copyfile} and L{default_mkdir}
    @return: True, or an exception is thrown on failure
        (OSError, although see default_copyfile for specifics).
    """

    iterate = iter
    if offset is not None:
        iterate = partial(offset_rewriter, offset.rstrip(os.path.sep))

    for x in iterate(cset.iterdirs(invert=True)):
        callback(x)
        try:
            os.unlink(x.location)
        except OSError, e:
            if e.errno != errno.ENOENT:
                raise
    # this is a fair sight faster then using sorted/reversed
    l = list(iterate(cset.iterdirs()))
    l.sort(reverse=True)
    for x in l:
        try:
            os.rmdir(x.location)
        except OSError, e:
            if not e.errno in (errno.ENOTEMPTY, errno.ENOENT, errno.ENOTDIR,
                               errno.EBUSY, errno.EEXIST):
                raise
        else:
            callback(x)
    return True

# Plugin system priorities
for func in [default_copyfile, default_ensure_perms, default_mkdir,
             merge_contents, unmerge_contents]:
    func.priority = 1
del func
