# Bazaar-NG -- distributed version control
#
# Copyright (C) 2006 by Canonical Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

"""Wrapper for readdir which grabs file type from d_type."""


import os, errno
from stat import S_ISDIR, S_ISREG


def listdir(path):
    return os.listdir(path)

def stat_swallow_enoent(path, check, default=False):
    try:
        return check(os.stat(path).st_mode)
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
    stat = os.stat
    return [x for x in os.listdir(path) if
        scheck(stat(pjoin(path, x)).st_mode)]

def listdir_files(path, followSymlinks=True):
    pjoin = os.path.join
    scheck = S_ISREG
    if followSymlinks:
        return [x for x in os.listdir(path) if
            stat_swallow_enoent(pjoin(path, x), scheck)]
    stat = os.stat
    return [x for x in os.listdir(path) if
        scheck(stat(pjoin(path, x)).st_mode)]
