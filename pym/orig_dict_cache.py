#!/usr/bin/python
# orig_dict_cache.py; older listdir caching implementation
# Copyright 1999-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#$Header$

"""per process caching of os.listdir returns.
Symlink unaware, so beware of webs of symlinks"""

import portage_util, os, stat
import portage_file

dircache = {}
cacheHit = 0
cacheMiss = 0
cacheStale = 0

def cacheddir(my_original_path):
	"""return results from cache, updating cache if its stale/incomplete"""
	global cacheHit, cacheMiss, cacheStale, dircache
	mypath=portage_file.normpath(my_original_path)
	if dircache.has_key(mypath):
		cacheHit += 1
		cached_mtime, list, ftype = dircache[mypath]
	else:
		cacheMiss += 1
		cached_mtime, list, ftype = -1, [], []
	pathstat = os.stat(mypath)
	if stat.S_ISDIR(pathstat[stat.ST_MODE]):
		mtime = pathstat[stat.ST_MTIME]
	else:
		raise Exception
	if mtime != cached_mtime:
		if dircache.has_key(mypath):
			cacheStale += 1
		list = os.listdir(mypath)
		ftype = []
		for x in list:
			try:
				pathstat = os.lstat(mypath+"/"+x)
				
				if stat.S_ISREG(pathstat[stat.ST_MODE]):
					ftype.append(0)
				elif stat.S_ISDIR(pathstat[stat.ST_MODE]):
					ftype.append(1)
				elif stat.S_ISLNK(pathstat[stat.ST_MODE]):
					pathstat = os.stat(mypath+"/"+x)
					if stat.S_ISREG(pathstat[stat.ST_MODE]):
						ftype.append(2)
					elif stat.S_ISDIR(pathstat[stat.ST_MODE]):
						ftype.append(3)
				else:
					ftype.append(4)

			except SystemExit, e:
				raise
			except:
				ftype.append(3)
		dircache[mypath] = mtime, list, ftype
	
	return list[:],ftype[:]

	portage_util.writemsg("cacheddirStats: H:%d/M:%d/S:%d\n" % (cacheHit, cacheMiss, cacheStale),10)
	return ret_list, ret_ftype
