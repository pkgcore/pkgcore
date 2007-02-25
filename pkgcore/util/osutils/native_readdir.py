# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""Wrapper for readdir which grabs file type from d_type."""


import os, errno
from stat import S_ISDIR, S_ISREG


def listdir(path):
    return os.listdir(path)

def stat_swallow_enoent(path, check, default=False, stat=os.stat):
    try:
        return check(stat(path).st_mode)
    except OSError, oe:
        if oe.errno == errno.ENOENT:
            return default
        raise

def listdir_dirs(path, followSymlinks=True):
    pjoin = os.path.join
    scheck = S_ISDIR
    if followSymlinks:
        return [x for x in os.listdir(path) if
            stat_swallow_enoent(pjoin(path, x), scheck)]
    lstat = os.lstat
    return [x for x in os.listdir(path) if
        scheck(lstat(pjoin(path, x)).st_mode)]

def listdir_files(path, followSymlinks=True):
    pjoin = os.path.join
    scheck = S_ISREG
    if followSymlinks:
        return [x for x in os.listdir(path) if
            stat_swallow_enoent(pjoin(path, x), scheck)]
    lstat = os.lstat
    return [x for x in os.listdir(path) if
        scheck(lstat(pjoin(path, x)).st_mode)]
