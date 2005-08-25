# rsync.py; module providing an abstraction over the rsync binary
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#$Id: rsync.py 1911 2005-08-25 03:44:21Z ferringb $

from portage_const import RSYNC_BIN, RSYNC_HOST
import os, portage_exec
import portage_exception,socket

import sync.syncexceptions

class RSyncSyntaxError(sync.syncexceptions.SyncException):
	"""Exception thrown when generated rsync syntax is invalid"""
	def __init__(self,command):
		self.command=command
	def __str__(self):
		return "Invalid rsync syntax: %s" % str(self.command)

class RsyncHost:
	"""abstraction over the rsync binary"""

	def __init__(self,host_uri,local_host=False,rsync_binary=RSYNC_BIN):
		"""self explanatory"""
		if not os.access(rsync_binary,os.X_OK):
			raise portage_exceptions.CommandNotFound(rsync_binary)

		self.__binary = rsync_binary
		self.__host = host_uri
		self.__ips = []

		self.__local = local_host
		if self.__local:
			self.__host_name=''
			self.__remote_path = host_uri
			self.__host_uri=''
			return

		f=host_uri.split("/",1)
		if len(f) == 1:
			#deprecated, assume /gentoo-portage
			self.__remote_path = "/gentoo-portage"
		else:
			self.__remote_path = "/"+f[1]
			host_uri = f[0]

		f=host_uri.find("@")
		if f != -1:
			host_uri=host_uri[f+1:]
		f=host_uri.find(":")
		if f != -1:
			host_uri=host_uri[:f]

		self.__host_name = host_uri

	def get_remote_path(self):
		return self.__remote_path

	def get_ips(self):
		if self.__local:
			return None
		try:
			self.__ips = socket.gethostbyname_ex(self.__host_name)[2]
		except socket.error,e:
			print "caught exception for %s" % self.__host_name,e
			return None
		return self.__ips
	
	def sync(self,settings, local_path,remote_path=None,verbosity=1,excludes=[],compress=True, \
		timeout=180,ip=None,cleanup=True):
		"""sync up local_path with remote_path on host
		settings is a portage.config, at some point hopefully removed and specific options
		passed in instead.
		verbosity ranges 0-4
		0 is absolutely quiet, 1 is quiet, 2 is normal, 3 is noisy.
		ip is used to control which ip of the host is used.
		cleanup controls deletion."""

		args=[self.__binary,
			"--recursive",    # Recurse directories
			"--links",        # Consider symlinks
			"--safe-links",   # Ignore links outside of tree
			"--perms",        # Preserve permissions
			"--times",        # Preserive mod times
			"--force",        # Force deletion on non-empty dirs
			"--whole-file",   # Don't do block transfers, only entire files
			"--stats",        # Show final statistics about what was transfered
			"--timeout="+str(timeout), # IO timeout if not done in X seconds
			]

		if cleanup:
			args.append("--delete")#       # Delete files that aren't in the master tree
			args.append("--delete-after")  # Delete only after everything else is done

		if compress:
			args.append("--compress")
		for x in excludes:
			args.append("--exclude=%s" % str(x))
		if verbosity >=3:
			args.append("--progress")
			args.append("--verbose")
		elif verbosity == 2:
			args.append("--progress")
		elif verbosity == 1:
			args.append("--quiet")
		else:
			args.append("--quiet")
			args.remove("--stats")

		if verbosity:
			fd_pipes={1:1,2:2}
		else:
			fd_pipes={}
		
		#why do this if has_key crap?  cause portage.config lacks a get function
		#this allows dicts to be passed in and used.
		if settings.has_key("RSYNC_INCLUDE"):
			for x in settings["RSYNC_INCLUDE"].split():
				args.append("--include=%s" % x)
		if settings.has_key("RSYNC_INCLUDEFROM"):
			for x in settings["RSYNC_INCLUDEFROM"].split():
				args.append("--include-from=%s" % x)
		if settings.has_key("RSYNC_EXCLUDE"):
			for x in settings["RSYNC_EXCLUDE"].split():
				args.append("--exclude=%s" % x)
		if settings.has_key("RSYNC_EXCLUDEFROM"):
			for x in settings["RSYNC_EXCLUDEFROM"].split():
				args.append("--exclude-from=%s" % x)

		if settings.has_key("RSYNC_RATELIMIT"):
			args.append("--bwlimit=%s" % settings["RSYNC_RATELIMIT"])

		prefix="rsync://"
		if remote_path == None:
			if self.__local:
				host=self.__remote_path
				prefix=''
			else:
				host=self.__host
		else:
			if remote_path[0] != "/":
				host = self.__host_name + '/' + remote_path
			else:
				host = self.__host_name + remote_path

		if ip:
			args.append("%s%s" % (prefix,host.replace(self.__host_name,ip)))
		else:
			args.append("%s%s" % (prefix,host))
		args.append(local_path)

		# tie a debug option into this
		#print "options are",args

		ret=portage_exec.spawn(args,fd_pipes=fd_pipes)
		if ret == 0:
			return True
		elif ret == 1:
			raise RSyncSyntaxError(args)
		elif ret == 11:
			raise IOError("Rsync returned exit code 11; disk space remaining?")
		return ret
