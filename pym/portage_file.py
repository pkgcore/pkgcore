# portage_file.py -- general fs stuff.  I think.
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$
cvs_id_string="$Id: portage_file.py 1696 2005-03-07 04:00:30Z ferringb $"[5:-2]

import os
import portage_data
import portage_exception
import orig_dict_cache
from portage_localization import _

def normpath(mypath):
	newpath = os.path.normpath(mypath)
	if len(newpath) > 1:
		if newpath[:2] == "//":
			newpath = newpath[1:]
	return newpath
								

def makedirs(path, perms=0755, uid=None, gid=None, must_chown=False):
	old_umask = os.umask(0)
	if(uid == None):
		uid = portage_data.portage_uid
	if(gid == None):
		gid = portage_data.portage_gid
	if not path:
		raise portage_exception.InvalidParameter, _("Invalid path: type: '%(type)s' value: '%(path)s'") % {"path": path, "type": type(path)}
	if(perm > 1535) or (perm == 0):
		raise portage_exception.InvalidParameter, _("Invalid permissions passed. Value is octal and no higher than 02777.")

	mypath = normpath(path)
	dirs = string.split(path, "/")
	
	mypath = ""
	if dirs and dirs[0] == "":
		mypath = "/"
		dirs = dirs[1:]
	for x in dirs:
		mypath += x+"/"
		if not os.path.exists(mypath):
			os.mkdir(mypath, perm)
			try:
				os.chown(mypath, uid, gid)
			except SystemExit, e:
				raise
			except:
				if must_chown:
					os.umask(old_umask)
					raise
				portage_util.writemsg(_("Failed to chown: %(path)s to %(uid)s:%(gid)s\n") % {"path":mypath,"uid":uid,"gid":gid})

	os.umask(old_umask)
	
def listdir(mypath, recursive=False, filesonly=False, ignorecvs=False, ignorelist=[], 
	followSymlinks=True, cacheObject=None):

	if cacheObject:
		cfunc = cacheObject.cacheddir
	else:
		cfunc = orig_dict_cache.cacheddir
	try:
		list, ftype = cfunc(mypath)
	except SystemExit:
		raise
	except Exception:
		return []

	if list is None:
		list=[]
	if ftype is None:
		ftype=[]

	if ignorecvs or len(ignorelist):
		x=0
		while x < len(list):
			#we're working with first level entries, no os.path.basename requirement
			if (ignorecvs and (list[x] in ('CVS','.svn') or list[x].startswith(".#"))) and not \
				list[x] in ignorelist:
				list.pop(x)
				ftype.pop(x)
				continue
			x += 1

	if not filesonly and not recursive:
		return list

	if recursive:
		x=0
		while x<len(ftype):
			b=os.path.basename(list[x])
			# if it was cvs, it was filtered already.
			if ftype[x] == 1 or (followSymlinks and ftype[x] == 3):

				l,f = cfunc(mypath+"/"+list[x])

				y=0
				while y < len(l):
					# use list comprehension here.
					if not (ignorecvs and (l[y] in ('CVS','.svn') or l[y].startswith(".#"))) \
						and not l[y] in ignorelist:
						l[y]=list[x]+"/"+l[y]
						y += 1
					else:
						l.pop(y)
						f.pop(y)

				list=list+l
				ftype=ftype+f
			x+=1
	if filesonly:
		rlist=[]
		for x in range(0,len(ftype)):
			if ftype[x]==0:
				rlist=rlist+[list[x]]
	else:
		rlist=list
			
	return rlist
