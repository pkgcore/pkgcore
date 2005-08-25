# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: fs.py 1911 2005-08-25 03:44:21Z ferringb $
cvs_id_string="$Id: fs.py 1911 2005-08-25 03:44:21Z ferringb $"[5:-2]

import os

def ensure_dirs(path, gid=-1, uid=-1, mode=0777):
	"""ensure dirs exist, creating as needed with (optional) gid, uid, and mode"""

	try:
		st = os.stat(path)
	except OSError:
		base = os.path.sep
		try:
			um = os.umask(0)
			for dir in os.path.abspath(path).split(os.path.sep):
				base = os.path.join(base,dir)
				if not os.path.exists(base):
					try:
						os.mkdir(base, mode)
						if gid != -1 or uid != -1:
							os.chown(base, uid, gid)
					except OSError:
						return False
		finally:
			os.umask(um)
		return True
	try:
		um = os.umask(0)
		try:
			if (gid != -1 and gid != st.st_gid) or (uid != -1 and uid != st.st_uid):
				os.chown(path, uid, gid)
			if mode != (st.st_mode & 04777):
				os.chmod(path, mode)
		except OSError:
			return False
	finally:
		os.umask(um)
	return True


# XXX throw this out.
try:
	#XXX: This should get renamed to bsd_chflags, I think.
	import chflags
	bsd_chflags = chflags
except SystemExit, e:
	raise
except:
	# XXX: This should get renamed to bsd_chflags, I think.
	bsd_chflags = None




# XXX throw this out.
def movefile(src,dest,newmtime=None,sstat=None,mysettings=None):
	"""moves a file from src to dest, preserving all permissions and attributes; mtime will
	be preserved even when moving across filesystems.  Returns true on success and false on
	failure.  Move is atomic."""
	#print "movefile("+str(src)+","+str(dest)+","+str(newmtime)+","+str(sstat)+")"
	from portage.spawn import selinux_capable
	import stat, shutil, os.path
	if selinux_capable:
		import selinux
	from portage.os_data import lchown
	try:
		if not sstat:
			sstat=os.lstat(src)
		if bsd_chflags:
			sflags=bsd_chflags.lgetflags(src)
			if sflags < 0:
				# Problem getting flags...
				print "!!! Couldn't get flags for "+dest+"\n"
				return None
			
	except SystemExit, e:
		raise
	except Exception, e:
		print "!!! Stating source file failed... movefile()"
		print "!!!",e
		return None

	destexists=1
	try:
		dstat=os.lstat(dest)
	except SystemExit, e:
		raise
	except:
		dstat=os.lstat(os.path.dirname(dest))
		destexists=0

	if bsd_chflags:
		# Check that we can actually unset schg etc flags...
		# Clear the flags on source and destination; we'll reinstate them after merging
		if(destexists):
			if bsd_chflags.lchflags(dest, 0) < 0:
				print "!!! Couldn't clear flags on file being merged: \n"
		# We might have an immutable flag on the parent dir; save and clear.
		pflags=bsd_chflags.lgetflags(os.path.dirname(dest))
		bsd_chflags.lchflags(os.path.dirname(dest), 0)
		
		# Don't bother checking the return value here; if it fails then the next line will catch it.
		bsd_chflags.lchflags(src, 0)
		
		if bsd_chflags.lhasproblems(src)>0 or (destexists and bsd_chflags.lhasproblems(dest)>0) or bsd_chflags.lhasproblems(os.path.dirname(dest))>0:
			# This is bad: we can't merge the file with these flags set.
			print "!!! Can't merge file "+dest+" because of flags set\n"
			return None		

	if destexists:
		if stat.S_ISLNK(dstat.st_mode):
			try:
				os.unlink(dest)
				destexists=0
			except SystemExit, e:
				raise
			except Exception, e:
				pass

	if stat.S_ISLNK(sstat.st_mode):
		try:
			target=os.readlink(src)
			if mysettings and mysettings["D"]:
				if target.find(mysettings["D"])==0:
					target=target[len(mysettings["D"]):]
			if destexists and not stat.S_ISDIR(dstat.st_mode):
				os.unlink(dest)
			if selinux_capable:
				sid = selinux.get_lsid(src)
				selinux.secure_symlink(target,dest,sid)
			else:
				os.symlink(target,dest)
			lchown(dest,sstat.st_uid, sstat.st_gid)
			if bsd_chflags:
				# Restore the flags we saved before moving
				if bsd_chflags.lchflags(dest, sflags) < 0 or bsd_chflags.lchflags(os.path.dirname(dest), pflags) < 0:
					writemsg("!!! Couldn't restore flags ("+str(flags)+") on " + dest+":\n")
					writemsg("!!! %s\n" % str(e))
					return None
			return os.lstat(dest).st_mtime
		except SystemExit, e:
			raise
		except Exception, e:
			print "!!! failed to properly create symlink:"
			print "!!!",dest,"->",target
			print "!!!",e
			return None

	renamefailed=1
	if sstat.st_dev == dstat.st_dev or selinux_capable:
		try:
			if selinux_capable:
				ret=selinux.secure_rename(src,dest)
			else:
				ret=os.rename(src,dest)
			renamefailed=0
		except SystemExit, e:
			raise
		except Exception, e:
			import errno
			if e[0]!=errno.EXDEV:
				# Some random error.
				print "!!! Failed to move",src,"to",dest
				print "!!!",e
				return None
			# Invalid cross-device-link 'bind' mounted or actually Cross-Device
	if renamefailed:
		didcopy=0
		if stat.S_ISREG(sstat.st_mode):
			try: # For safety copy then move it over.
				if selinux_capable:
					selinux.secure_copy(src,dest+"#new")
					selinux.secure_rename(dest+"#new",dest)
				else:
					shutil.copyfile(src,dest+"#new")
					os.rename(dest+"#new",dest)
				didcopy=1
			except SystemExit, e:
				raise
			except Exception, e:
				print '!!! copy',src,'->',dest,'failed.'
				print "!!!",e
				return None
		else:
			#we don't yet handle special, so we need to fall back to /bin/mv
			if selinux_capable:
				a=portage_exec.spawn_get_output(MOVE_BINARY+" -c -f '%s' '%s'" % (src,dest))
			else:
				a=portage_exec.spawn_get_output(MOVE_BINARY+" -f '%s' '%s'" % (src,dest))
				if a[0]!=0:
					print "!!! Failed to move special file:"
					print "!!! '"+src+"' to '"+dest+"'"
					print "!!!",a
					return None # failure
		try:
			if didcopy:
				lchown(dest,sstat.st_uid, sstat.st_gid)
				os.chmod(dest, stat.S_IMODE(sstat.st_mode)) # Sticky is reset on chown
				os.unlink(src)
		except SystemExit, e:
				os.unlink(src)
		except SystemExit, e:
			raise
		except Exception, e:
			print "!!! Failed to chown/chmod/unlink in movefile()"
			print "!!!",dest
			print "!!!",e
			return None

	if newmtime:
		os.utime(dest,(newmtime,newmtime))
	else:
		os.utime(dest, (sstat.st_atime, sstat.st_mtime))
		newmtime=sstat.st_mtime

	if bsd_chflags:
		# Restore the flags we saved before moving
		if bsd_chflags.lchflags(dest, sflags) < 0 or bsd_chflags.lchflags(os.path.dirname(dest), pflags) < 0:
			writemsg("!!! Couldn't restore flags ("+str(sflags)+") on " + dest+":\n")
			return None
		
	return newmtime


def abssymlink(symlink):
	"""
	This reads symlinks, resolving the relative symlinks, and returning the absolute.
	"""
	import os.path
	mylink=os.readlink(symlink)
	if mylink[0] != '/':
		mydir=os.path.dirname(symlink)
		mylink=mydir+"/"+mylink
	return os.path.normpath(mylink)


def normpath(mypath):
	newpath = os.path.normpath(mypath)
	if len(newpath) > 1:
		if newpath[:2] == "//":
			return newpath[1:]
	return newpath
