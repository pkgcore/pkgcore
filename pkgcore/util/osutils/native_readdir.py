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


import os
from stat import S_ISDIR, S_ISREG


def native_listdir(path):
	return os.listdir(path)

def native_listdir_dirs(path, followSymlinks=True):
	pjoin = os.path.join
	if followSymlinks:
		stat = os.stat
	else:
		stat = os.lstat
	return [x for x in os.listdir(path) if S_ISDIR(stat(pjoin(path, x)).st_mode)]

def native_listdir_files(path, followSymlinks=True):
	pjoin = os.path.join
	if followSymlinks:
		stat = os.stat
	else:
		stat = os.lstat
	return [x for x in os.listdir(path) if not S_ISDIR(stat(pjoin(path, x)).st_mode)]
