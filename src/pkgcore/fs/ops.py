"""
default fs ops.

Shouldn't be accessed directly for the most part, use
:mod:`pkgcore.plugins` to get at these ops.
"""

import errno
import os
from functools import partial

from snakeoil.osutils import ensure_dirs, pjoin, unlink_if_exists
from snakeoil.process.spawn import spawn

from ..const import CP_BINARY
from ..plugin import get_plugin
from . import contents, fs
from .livefs import gen_obj

__all__ = [
    "merge_contents", "unmerge_contents", "default_ensure_perms",
    "default_copyfile", "default_mkdir"]


def default_ensure_perms(d1, d2=None):

    """Enforce a fs objects attributes on the livefs.

    Attributes enforced are permissions, mtime, uid, gid.

    :param d2: if not None, an fs object for what's on the livefs now
    :return: True on success, else an exception is thrown
    :raise EnvironmentError: if fs object attributes can't be enforced
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
                # if it's preexisting, keep its perms.
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
    if not fs.issym(d1):
        if do_mode and m is not None:
            os.chmod(d1.location, m)
        if do_mtime and t is not None:
            os.utime(d1.location, (t, t))
    return True


def default_mkdir(d):
    """
    mkdir for a fsDir object

    :param d: :class:`pkgcore.fs.fs.fsDir` instance
    :return: true if success, else an exception is thrown
    :raise EnvironmentError: if can't complete
    """
    if not d.mode:
        mode = 0o777
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
        return f'failed copying {self.obj}: {self.msg}'


class CannotOverwrite(FailedCopy):
    def __init__(self, obj, existing):
        self.obj, self.existing = obj, existing

    def __str__(self):
        return f'cannot write {self.obj} due to {self.existing} existing'


def default_copyfile(obj, mkdirs=False):
    """
    copy a :class:`pkgcore.fs.fs.fsBase` to its stated location.

    :param obj: :class:`pkgcore.fs.fs.fsBase` instance, exempting :class:`fsDir`
    :return: true if success, else an exception is thrown
    :raise EnvironmentError: permission errors

    """

    existent = False
    ensure_perms = get_plugin("fs_ops.ensure_perms")
    if not fs.isfs_obj(obj):
        raise TypeError(f'obj must be fsBase derivative: {obj!r}')
    elif fs.isdir(obj):
        raise TypeError(f'obj must not be a fsDir instance: {obj!r}')

    try:
        existing = gen_obj(obj.location)
        if fs.isdir(existing):
            raise CannotOverwrite(obj, existing)
        existent = True
    except OSError as oe:
        # verify the parent dir is there at least
        basefp = os.path.dirname(obj.location)
        if basefp.strip(os.path.sep) and not os.path.exists(basefp):
            if mkdirs:
                if not ensure_dirs(basefp, mode=0o750, minimal=True):
                    raise FailedCopy(obj, str(oe))
            else:
                raise
        existent = False

    if not existent:
        fp = obj.location
    else:
        fp = existent_fp = obj.location + "#new"

    if fs.isreg(obj):
        obj.data.transfer_to_path(fp)
    elif fs.issym(obj):
        os.symlink(obj.target, fp)
    elif fs.isfifo(obj):
        os.mkfifo(fp)
    elif fs.isdev(obj):
        dev = os.makedev(obj.major, obj.minor)
        os.mknod(fp, obj.mode, dev)
    else:
        ret = spawn([CP_BINARY, "-Rp", obj.location, fp])
        if ret != 0:
            raise FailedCopy(obj, f'got {ret} from {CP_BINARY} -Rp')

    ensure_perms(obj.change_attributes(location=fp))

    if existent:
        os.rename(existent_fp, obj.location)
    return True

def do_link(src, trg):
    try:
        os.link(src.location, trg.location)
        return True
    except FileExistsError:
        pass
    except EnvironmentError as e:
        if e.errno == errno.EXDEV:
            # hardlink is impossible, force copyfile
            return False
        raise

    path = trg.location + '#new'
    unlink_if_exists(path)
    try:
        os.link(src.location, path)
    except EnvironmentError as e:
        if e.errno != errno.EXDEV:
            # someone is screwing with us, or unlink_if_exists is broken.
            raise
        # hardlink is impossible, force copyfile
        return False
    try:
        os.rename(path, trg.location)
    except EnvironmentError:
        unlink_if_exists(path)
        if e.eerrno != errno.EXDEV:
            # weird error, broken FS codes, perms, or someone is screwing with us.
            raise
        # this is only possible on overlay fs's; while annoying, you can have two
        # different filesystems in use in the same directory in those cases.
        return False
    return True


def merge_contents(cset, offset=None, callback=None):

    """
    merge a :class:`pkgcore.fs.contents.contentsSet` instance to the livefs

    :param cset: :class:`pkgcore.fs.contents.contentsSet` instance
    :param offset: if not None, offset to prefix all locations with.
        Think of it as target dir.
    :param callback: callable to report each entry being merged; given a single arg,
        the fs object being merged.
    :raise EnvironmentError: Thrown for permission failures.
    """

    if callback is None:
        callback = lambda obj:None

    ensure_perms = get_plugin("fs_ops.ensure_perms")
    copyfile = get_plugin("fs_ops.copyfile")
    mkdir = get_plugin("fs_ops.mkdir")

    if not isinstance(cset, contents.contentsSet):
        raise TypeError(f'cset must be a contentsSet, got {cset!r}')

    if offset is not None:
        if os.path.exists(offset):
            if not os.path.isdir(offset):
                raise TypeError(f'offset must be a dir, or not exist: {offset}')
        else:
            mkdir(fs.fsDir(offset, strict=False))
        iterate = partial(contents.offset_rewriter, offset.rstrip(os.path.sep))
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
            obj = gen_obj(x.location, stat=os.stat(x.location))
            if not fs.isdir(obj):
                # according to the spec, dirs can't be merged over files
                # that aren't dirs or symlinks to dirs
                raise CannotOverwrite(x.location, obj)
            ensure_perms(x, obj)
        except FileNotFoundError:
            try:
                # we do this form to catch dangling symlinks
                mkdir(x)
            except FileExistsError:
                os.unlink(x.location)
                mkdir(x)
            ensure_perms(x)
    del d

    # might look odd, but what this does is minimize the try/except cost
    # to one time, assuming everything behaves, rather then per item.
    i = iterate(cset.iterdirs(invert=True))
    merged_inodes = {}
    while True:
        try:
            for x in i:
                callback(x)

                if x.is_reg:
                    key = (x.dev, x.inode)
                    # This logic could be made smarter- instead of
                    # blindly trying candidates, we could inspect the st_dev
                    # of the final location.  This however can be broken by
                    # overlayfs's potentially.  Brute force is in use either
                    # way.
                    candidates = merged_inodes.setdefault(key, [])
                    if any(target._can_be_hardlinked(x) and do_link(target, x)
                            for target in candidates):
                        continue
                    candidates.append(x)

                copyfile(x, mkdirs=True)

            break
        except CannotOverwrite as cf:
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


def unmerge_contents(cset, offset=None, callback=None):

    """
    unmerge a :obj:`pkgcore.fs.contents.contentsSet` instance to the livefs

    :param cset: :obj:`pkgcore.fs.contents.contentsSet` instance
    :param offset: if not None, offset to prefix all locations with.
        Think of it as target dir.
    :param callback: callable to report each entry being unmerged
    :return: True, or an exception is thrown on failure
        (OSError, although see default_copyfile for specifics).
    :raise EnvironmentError: see :func:`default_copyfile` and :func:`default_mkdir`
    """

    if callback is None:
        callback = lambda obj: None

    iterate = iter
    if offset is not None:
        iterate = partial(contents.offset_rewriter, offset.rstrip(os.path.sep))

    for x in iterate(cset.iterdirs(invert=True)):
        callback(x)
        unlink_if_exists(x.location)

    # this is a fair sight faster then using sorted/reversed
    l = list(iterate(cset.iterdirs()))
    l.sort(reverse=True)
    for x in l:
        try:
            os.rmdir(x.location)
        except OSError as e:
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
