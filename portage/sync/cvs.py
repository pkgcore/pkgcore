# cvs.py; provides cvs sync capabilities, encapsulates the necessary cvs binary calls
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#$Header$

import os, stat
from portage.spawn import spawn, spawn_bash, CommandNotFound
#import sync
from portage.const import CVS_BIN

import sync.syncexceptions
class CVSIOError(sync.syncexceptions.SyncException):
	def __init__(self,errmsg,command):
		self.errmsg=errmsg
		self.command=command
	def __str__(self):
		return "cvs error: command %s, %s" % (self.command, self.errmsg)

class CvsHost:
	def __init__(self,host_uri,cvs_binary=CVS_BIN):
		if not os.access(cvs_binary, os.X_OK):
			raise CommandNotFound(cvs_binary)
		self.__binary=cvs_binary
		#parse the bugger.
		#new format.
		#cvs://[CVS_RSH binary:]user@host:cvs_root:module
		#example
		#cvs://ssh:ferringb@dev.gentoo.org:/var/cvsroot:gentoo-x86
		#old format
		#cvs://user@host:cvsroot
		#implicit gentoo-x86 module, and ext w/ ssh.
		#here we go. :/

		if host_uri.count(":") >= 2:
			self.__init_new_host_uri(host_uri)
		else:
			self.__init_deprecated_uri(host_uri)

	def __init_new_host_uri(self,host):
		#cvs://ssh:ferringb@dev.gentoo.org:/var/cvsroot:gentoo-x86
		s=host.split(":")
		if len(s) == 4:
			self.__ext=s.pop(0)
			s[0] = ":ext:" + s[0]
		else:
			self.__ext=None
		self.__cvsroot=s[0]+":"+s[1]
		self.__cvsmodule=s[2]

	def __init_deprecated_uri(self,host):
		self.__ext="ssh"
		self.__cvsmodule="gentoo-x86"
		self.__cvsroot=host

	def sync(self,local_path,verbosity=1,compress=False):
		while local_path[-1] == "/":
			local_path = local_path[:-1]
		if compress:
			c_arg='-z9'
		else:
			c_arg=''

		env={}
		if self.__ext:
			env = {"CVS_RSH":self.__ext}
		
		l=len(self.__cvsmodule)
		if not os.path.exists(local_path):
			newdir=os.path.basename(local_path)
			basedir=local_path[:-len(newdir)]
			if os.path.exists(basedir+"/"+self.__cvsmodule):
				raise Exception("unable to checkout to %s, module directory %s exists already" % \
					(basedir, self.__cvsmodule))
			elif os.path.exists(basedir+"/CVS"):
				raise Exception("unable to checkout to %s, a CVS directory exists w/in already" % basedir)
			command="cd '%s' ; %s %s -d %s co -P  %s" % \
				(basedir, self.__binary, c_arg, self.__cvsroot, self.__cvsmodule)

			ret=spawn_bash(command,env=env,opt_name="cvs co")
			if ret:
				raise CVSIOError("failed checkout",command)
			if newdir != self.__cvsmodule:
				ret = spawn(('mv','%s/%s' % (basedir,self.__cvsmodule),local_path))
				if ret:
					raise Exception("failed moving %s/%s to %s" % (basedir,self.__cvsmodule,local_path))
		elif stat.S_ISDIR(os.stat(local_path).st_mode):

			command="cd '%s'; %s %s -d %s up" % (local_path, self.__binary, c_arg,self.__cvsroot)
			ret = spawn_bash(command, env=env,opt_name="cvs up")
			if ret:
				raise CVSIOError("failed updated", command)
		else:
			raise Exception("%s exists, and is not a directory.  rectify please" % local_path)
		return True

