#!/usr/bin/python
# ebuild.py; Ebuild classes/abstraction of phase processing, and communicating with a ebuild-daemon.sh instance
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#$Header$

# this will die a horrible death soon.
# held onto strictly for the doebuild type info.

import os,sys,traceback
import portage_const,types
#still needed?
from portage_const import *
import portage_locks, portage_util
import portage_exec
import portage_versions
import shutil, anydbm
import stat
import string

def shutdown_all_processors():
	"""kill off all known processors"""
	global active_ebp_list, inactive_ebp_list
	if type(active_ebp_list) != types.ListType:
		print "warning, ebuild.active_ebp_list wasn't a list."
		active_ebp_list = []
	if type(inactive_ebp_list) != types.ListType:
		print "warning, ebuild.inactive_ebp_list wasn't a list."
		inactive_ebp_list = []
	while len(active_ebp_list) > 0:
		try:	active_ebp_list[0].shutdown_processor()
		except (IOError,OSError):
			active_ebp_list.pop(0)
			continue
		try:			active_ebp_list.pop(0)
		except IndexError:	pass
	while len(inactive_ebp_list) > 0:
		try:
			inactive_ebp_list[0].shutdown_processor()
		except (IOError,OSError):
			inactive_ebp_list.pop(0)
			continue
		try:			inactive_ebp_list.pop(0)
		except IndexError:	pass


inactive_ebp_list = []
active_ebp_list = []

def request_ebuild_processor(config,ebuild_daemon_path=portage_const.EBUILD_DAEMON_PATH,userpriv=False, \
	sandbox=None,fakeroot=False,save_file=None):
	"""request an ebuild_processor instance from the pool, or create a new one
	  this walks through the requirements, matching a inactive processor if one exists
	  note fakerooted processors are never reused, do to the nature of fakeroot"""

	if sandbox == None:
		sandbox = portage_exec.sandbox_capable

	global inactive_ebp_list, active_ebp_list
	if not fakeroot:
		for x in inactive_ebp_list:
			if not x.locked() and x.ebd == ebuild_daemon_path and \
				x.userprived() == userpriv and (x.sandboxed() or not sandbox):
				inactive_ebp_list.remove(x)
				active_ebp_list.append(x)
				return x
	active_ebp_list.append(ebuild_processor(config, userpriv=userpriv,sandbox=sandbox,fakeroot=fakeroot,save_file=save_file))
	return active_ebp_list[-1]

def release_ebuild_processor(ebp):
	"""the inverse of request_ebuild_processor.  Any processor requested via request_ebuild_processor
	_must_ be released via this function once it's no longer in use.
	this includes fakerooted processors.
	Returns True exempting when the processor requested to be released isn't marked as active"""

	global inactive_ebp_list, active_ebp_list
	try:	active_ebp_list.remove(ebp)
	except ValueError:	return False

	try:	inactive_ebp_list.index(ebp)
	except ValueError:	
		# if it's a fakeroot'd process, we throw it away.  it's not useful outside of a chain of calls
		if not ebp.onetime():
			inactive_ebp_list.append(ebp)
		else:
			del ebp
		return True

	# if it makes it this far, that means ebp was already in the inactive list.
	# which is indicative of an internal fsck up.
	import traceback
	print "ebp was requested to be free'd, yet it already is claimed inactive _and_ was in the active list"
	print "this means somethings horked, badly"
	traceback.print_stack()
	return False
		


class ebuild_processor:
	"""abstraction of a running ebuild.sh instance- the env, functions, etc that ebuilds expect."""
	def __init__(self, config, ebuild_daemon_path=portage_const.EBUILD_DAEMON_PATH,userpriv=False, sandbox=True, \
		fakeroot=False,save_file=None):
		"""ebuild_daemon_path shouldn't be fooled with unless the caller knows what they're doing.
		sandbox enables a sandboxed processor
		userpriv enables a userpriv'd processor
		fakeroot enables a fakeroot'd processor- this is a mutually exclusive option to sandbox, and 
		requires userpriv to be enabled.  Violating this will result in nastyness"""

		self._config = config
		self.ebd = ebuild_daemon_path
		from portage_data import portage_uid, portage_gid
		spawn_opts = {}

		if fakeroot and (sandbox or not userpriv):
			import traceback
			traceback.print_stack()
			print "warning, was asking to enable fakeroot but-"
			print "sandbox",sandbox,"userpriv",userpriv
			print "this isn't valid.  bailing"
			raise Exception,"cannot initialize with sandbox and fakeroot"

		if userpriv:
			self.__userpriv = True
			spawn_opts.update({"uid":portage_uid,"gid":portage_gid,"groups":[portage_gid],"umask":002})
		else:
			if portage_exec.userpriv_capable:
				spawn_opts.update({"gid":portage_gid,"groups":[0,portage_gid]})
			self.__userpriv = False

		# open the pipes to be used for chatting with the new daemon
		cread, cwrite = os.pipe()
		dread, dwrite = os.pipe()
		self.__sandbox = False
		self.__fakeroot = False
		
		# since it's questionable which spawn method we'll use (if sandbox or fakeroot fex), 
		# we ensure the bashrc is invalid.
		env={"BASHRC":"/etc/portage/spork/not/valid/ha/ha"}
		args = []
		if sandbox:
			if fakeroot:
				print "!!! ERROR: fakeroot was on, but sandbox was also on"
				sys.exit(1)
			self.__sandbox = True
			spawn_func = portage_exec.spawn_sandbox
			env.update({"SANDBOX_DEBUG":"1","SANDBOX_DEBUG_LOG":"/var/tmp/test"})

		elif fakeroot:
			self.__fakeroot = True
			spawn_func = portage_exec.spawn_fakeroot
			args.append(save_file)
		else:
			spawn_func = portage_exec.spawn

		self.pid = spawn_func(self.ebd+" daemonize", fd_pipes={0:0, 1:1, 2:2, 3:cread, 4:dwrite},
			returnpid=True,env=env, *args, **spawn_opts)[0]

		os.close(cread)
		os.close(dwrite)
		self.ebd_write = os.fdopen(cwrite,"w")
		self.ebd_read  = os.fdopen(dread,"r")

		# basically a quick "yo" to the daemon
		self.write("dude?")
		if not self.expect("dude!"):
			print "error in server coms, bailing."
			raise Exception("expected 'dude!' response from ebd, which wasn't received. likely a bug")
		if self.__sandbox:
			self.write("sandbox_log?")
			self.__sandbox_log = self.read().split()[0]
		self.dont_export_vars=self.read().split()
		# locking isn't used much, but w/ threading this will matter
		self.unlock()

	def sandboxed(self):
		"""is this instance sandboxed?"""
		return self.__sandbox

	def userprived(self):
		"""is this instance userprived?"""
		return self.__userpriv

	def fakerooted(self):
		"""is this instance fakerooted?"""
		return self.__fakeroot

	def onetime(self):
		"""is this instance going to be discarded after usage; eg is it fakerooted?"""
		return self.__fakeroot

	def write(self, string,flush=True):
		"""talk to running daemon.  Disabling flush is useful when dumping large amounts of data
		all strings written are automatically \\n terminated"""
		if string[-1] == "\n":
			self.ebd_write.write(string)
		else:
			self.ebd_write.write(string +"\n")
		if flush:
			self.ebd_write.flush()
		
	def expect(self, want):
		"""read from the daemon, and return true or false if the returned string is what is expected"""
		got=self.ebd_read.readline()
		return want==got[:-1]

	def read(self,lines=1):
		"""read data from the daemon.  Shouldn't be called except internally"""
		mydata=''
		while lines > 0:
			mydata += self.ebd_read.readline()
			lines -= 1
		return mydata

	def sandbox_summary(self, move_log=False):
		"""if the instance is sandboxed, print the sandbox access summary"""
		if not os.path.exists(self.__sandbox_log):
			self.write("end_sandbox_summary")
			return 0
		violations=portage_util.grabfile(self.__sandbox_log)
		if len(violations)==0:
			self.write("end_sandbox_summary")
			return 0
		if not move_log:
			move_log=self.__sandbox_log
		elif move_log != self.__sandbox_log:
			myf=open(move_log)
			for x in violations:
				myf.write(x+"\n")
			myf.close()
		from output import red
		self.ebd_write.write(red("--------------------------- ACCESS VIOLATION SUMMARY ---------------------------")+"\n")
		self.ebd_write.write(red("LOG FILE = \"%s\"" % move_log)+"\n\n")
		for x in violations:
			self.ebd_write.write(x+"\n")
		self.write(red("--------------------------------------------------------------------------------")+"\n")
		self.write("end_sandbox_summary")
		try:
			os.remove(self.__sandbox_log)
		except (IOError, OSError), e:
			print "exception caught when cleansing sandbox_log=%s" % str(e)
		return 1
		
	def preload_eclasses(self, ec_file):
		"""this preloades eclasses into a function, thus avoiding the cost of going to disk.
		preloading eutils (which is heaviliy inherited) speeds up regen times fex"""
		if not os.path.exists(ec_file):
			return 1
		self.write("preload_eclass %s" % ec_file)
		if self.expect("preload_eclass succeeded"):
			self.preloaded_eclasses=True
			return True
		return False

	def lock(self):
		"""lock the processor.  Currently doesn't block any access, but will"""
		self.processing_lock = True

	def unlock(self):
		"""unlock the processor"""
		self.processing_lock = False

	def locked(self):
		"""is the processor locked?"""
		return self.processing_lock

	def is_alive(self):
		"""returns if it's known if the processor has been shutdown.
		Currently doesn't check to ensure the pid is still running, yet it should"""
		return self.pid != None

	def shutdown_processor(self):
		"""tell the daemon to shut itself down, and mark this instance as dead"""
		try:
			if self.is_alive():
				self.write("shutdown_daemon")
				self.ebd_write.close()
				self.ebd_read.close()

				# now we wait.
				os.waitpid(self.pid,0)
		except (IOError,OSError,ValueError):
			pass

		# we *really* ought to modify portageatexit so that we can set limits for waitpid.
		# currently, this assumes all went well.
		# which isn't always true.
		self.pid = None

	def set_sandbox_state(self,state):
		"""tell the daemon whether to enable the sandbox, or disable it"""
		if state:
			self.write("set_sandbox_state 1")
		else:
			self.write("set_sandbox_state 0")

	def send_env(self):
		"""essentially transfer the ebuild's desired env to the running daemon
		accepts a portage.config instance, although it will accept dicts at some point"""
		be=self._config.bash_environ()
		self.write("start_receiving_env\n")
		exported_keys = ''
		for x in be.keys():
			if x not in self.dont_export_vars:
				self.write("%s=%s\n" % (x,be[x]), flush=False)
				exported_keys += x+' '
		self.write("export "+exported_keys,flush=False)
		self.write("end_receiving_env")
		return self.expect("env_received")
	
	def set_logfile(self,logfile=''):
		"""relevant only when the daemon is sandbox'd, set the logfile"""
		self.write("logging %s" % logfile)
		return self.expect("logging_ack")
	
	
	def __del__(self):
		"""simply attempts to notify the daemon to die"""
		# for this to be reached means we ain't in a list no more.
		if self.pid:
			self.shutdown_processor()


class ebuild_handler:
	"""abstraction of ebuild phases, fetching exported keys, fetching srcs, etc"""
	import portageq
	def __init__(self, config, process_limit=5):
		"""process_limit is currently ignored"""
		self.processed = 0
		self.__process_limit = process_limit
		self.preloaded_eclasses = False
		self._config = config
		self.__ebp = None

	def __del__(self):
		"""only ensures any processors this handler has claimed are released"""
		if self.__ebp:
			release_ebuild_processor(self.__ebp)

	# this is an implementation of stuart's confcache/sandbox trickery, basically the file/md5 stuff implemented in 
	# python with a basic bash wrapper that calls back to this.
	# all credit for the approach goes to him, as stated, this is just an implementation of it.
	# bugs should be thrown at ferringb.
	def load_confcache(self,transfer_to,confcache=portage_const.CONFCACHE_FILE,
		confcache_list=portage_const.CONFCACHE_LIST):
		"""verifys a requested conf cache, removing the global cache if it's stale.
		The handler should be the only one to call this"""
		from portage_checksum import perform_md5
		from output import red
		if not self.__ebp:
			import traceback
			traceback.print_stack()
			print "err... no ebp, yet load_confcache called. invalid"
			raise Exception,"load_confcache called yet no running processor.  bug?"

		valid=True
		lock=None
		if not os.path.exists(confcache_list):
			print "confcache file listing doesn't exist"
			valid=False
		elif not os.path.exists(confcache):
			print "confcache doesn't exist"
			valid=False
		else:
			lock=portage_locks.lockfile(confcache_list,wantnewlockfile=1)
			try:
				myf=anydbm.open(confcache_list, "r", 0664)
				for l in myf.keys():
					# file, md5
					if perform_md5(l,calc_prelink=1) != myf[l]:
						print red("***")+" confcache is stale: %s: recorded md5: %s: actual: %s:" % (l,myf[l],perform_md5(l,calc_prelink=1))
						raise Exception("md5 didn't match")
				myf.close()
				# verify env now.
				new_cache=[]
				env_vars=[]
				
				# guessing on THOST.  I'm sure it's wrong...

				env_translate={"build_alias":"CBUILD","host_alias":"CHOST","target_alias":"THOST"}
				cache=portage_util.grabfile(confcache)

				x=0
				while x < len(cache):
					#ac_cv_env
					if cache[x][0:10] == "ac_cv_env_":
						f=cache[x][10:].find("_set")
						if f == -1 or f==11:
							cache.pop(x)
							continue
						env_vars.append(cache[x][10:10 + cache[x][10:].find("_set")])
						x += 1
					else:
						new_cache.append(cache[x])
					x += 1

				for x in env_vars:
					self.__ebp.write("request %s" % env_translate.get(x,x))
					line=self.__ebp.read()
					if line[-1] == "\n":
						line=line[:-1]
					new_cache.append("ac_cv_env_%s_set=%s" % (x, line))
					if line == "unset":
						new_cache.append("ac_cv_env_%s_value=" % x)
					else:
						line=self.__ebp.read()
						if line[-1] == "\n":
							line=line[:-1]
						if line.split()[0] != line:
							#quoting... XXX
							new_cache.append("ac_cv_env_%s_value='%s'" % (x,line))
						else:
							new_cache.append("ac_cv_env_%s_value=%s" % (x,line))

				myf=open(confcache,"w")
				for x in new_cache:
					myf.write(x+"\n")
				myf.close()
						
			except SystemExit, e:
				raise
			except Exception,e:
				print "caught exception: %s" % str(e)
				try:	myf.close()
				except (IOError, OSError):	pass
				valid=False

		if not valid:
			print "\nconfcache is invalid\n"
			try:		os.remove(confcache_list)
			except OSError: pass
			try:		os.remove(confcache)
			except OSError:	pass
			self.__ebp.write("empty")
			valid=0
		else:
			self.__ebp.write("location: %s" % confcache)
			valid=1
		if lock:
			portage_locks.unlockfile(lock)
		return valid

	def update_confcache(self,settings,logfile,new_confcache, confcache=portage_const.CONFCACHE_FILE, \
		confcache_list=portage_const.CONFCACHE_LIST):
		"""internal function called when a processor has finished a configure, and wishes its cache
		be transferred to the global cache
		This runs through the sandbox log, storing the md5 of files along with the list of files to check.
		Finally, it transfers the cache to the global location."""

		if not self.__ebp:
			import traceback
			traceback.print_stack()
			print "err... no ebp, yet load_confcache called. invalid"
			sys.exit(1)

		import re
		from portage_checksum import perform_md5
		if not (os.path.exists(logfile) and os.path.exists(new_confcache)) :
			# eh?  wth?
			self.__ebp.write("failed")
			return 0
		myfiles=portage_util.grabfile(logfile)
		filter=re.compile('^(%s|/tmp|/dev|.*/\.ccache)/' % os.path.normpath(settings["PORTAGE_TMPDIR"]))
		l=[]
		for x in myfiles:
			# get only read syscalls...
			if x[0:8] == "open_rd:":
				l.append(x.split()[1])

		myfiles = portage_util.unique_array(l)
		l=[]
		for x in myfiles:
			if not os.path.exists(x):
				continue
			if not filter.match(x):
				l.append(x)
		del myfiles

		if not len(l):
			self.__ebp.write("updated")
			return 0

		lock=portage_locks.lockfile(confcache_list,wantnewlockfile=1)
		# update phase.
		if not os.path.exists(confcache_list):
			prevmask=os.umask(0)
			myf=anydbm.open(confcache_list,"n",0664)
			os.umask(prevmask)
		else:
			myf=anydbm.open(confcache_list,"w",0664)

		for x in l:
			try:
				if not stat.S_ISDIR(os.stat(x).st_mode) and not myf.has_key(x):
					myf[x]=str(perform_md5(x,calc_prelink=1))
			except (IOError, OSError):
				# exceptions are only possibly (ignoring anydbm horkage) from os.stat
				pass
		myf.close()
		from portage_data import portage_gid
		os.chown(confcache_list, -1, portage_gid)
		shutil.move(new_confcache, confcache)
		os.chown(confcache, -1, portage_gid)
		m=os.umask(0)
		os.chmod(confcache, 0664)
		os.chmod(confcache_list, 0664)
		os.umask(m)
		portage_locks.unlockfile(lock)
		self.__ebp.write("updated")
		return 0

	def get_keys(self,myebuild,myroot="/"):
		"""request the auxdbkeys from an ebuild
		returns a dict when successful, None when failed"""
#		print "getting keys for %s" % myebuild
		# normally,
		# userpriv'd, minus sandbox.  which is odd.
		# I say both, personally (and I'm writing it, so live with it)
		if self.__ebp:
			import traceback
			traceback.print_stack()
			print "self.__ebp exists. it shouldn't.  this indicates a handler w/ an active ebp never"
			print "released it, or a bug in the calls"
			sys.exit(1)


		self.__ebp = request_ebuild_processor(self._config, userpriv=portage_exec.userpriv_capable)

		if self.__adjust_env("depend",myebuild,myroot):
			return {}

		self.__ebp.write("process_ebuild depend")
		self.__ebp.send_env()
		self.__ebp.set_sandbox_state(True)
		self.__ebp.write("start_processing")
		line=self.__generic_phase(["sending_keys"], interpret_results=False)
		if line != "sending_keys":
			return None
		mykeys={}
		while line != "end_keys":
			line=self.__ebp.read()
			line=line[:-1]
			if line == "failed":
				self.__ebp.unlock()
				return {}
			if line == "end_keys" or not len(line):
				continue
			pair = line.split('=',1)
			mykeys[pair[0]]=pair[1]
		self.__ebp.expect("phases succeeded")
		if not release_ebuild_processor(self.__ebp):
			self.__ebp = None
			raise Exception,"crud"
		self.__ebp = None
		return mykeys

	def __adjust_env(self,mydo,myebuild,myroot,debug=0,listonly=0,fetchonly=0,cleanup=0,dbkey=None,\
			use_cache=1,fetchall=0,tree="porttree",use_info_env=True,verbosity=0):
		"""formerly portage.doebuild, since it's specific to ebuilds, it's now a method of ebuild handling.
		severely gutted, and in need of cleansing/exorcism"""
		from portage import db,ExtractKernelVersion,fetch,features, \
			digestgen,digestcheck,root,flatten, digestParseFile
		from portage_data import portage_uid,portage_gid,secpass
		import portage_dep
		from portage_util import writemsg

		ebuild_path = os.path.abspath(myebuild)
		pkg_dir     = os.path.dirname(ebuild_path)
	
		if self._config.configdict["pkg"].has_key("CATEGORY"):
			cat = self._config.configdict["pkg"]["CATEGORY"]
		else:
			cat         = os.path.basename(os.path.normpath(pkg_dir+"/.."))
		mypv        = os.path.basename(ebuild_path)[:-7]
		mycpv       = cat+"/"+mypv
	
		mysplit=portage_versions.pkgsplit(mypv,silent=0)
		if mysplit==None:
			writemsg("!!! Error: PF is null '%s'; exiting.\n" % mypv)
			return 1

		if mydo == "clean":
			cleanup=True
	
		if mydo != "depend":
			# XXX: We're doing a little hack here to curtain the gvisible locking
			# XXX: that creates a deadlock... Really need to isolate that.
			self._config.reset(use_cache=use_cache)
			
		self._config.setcpv(mycpv,use_cache=use_cache)
	
		if not os.path.exists(myebuild):
			writemsg("!!! doebuild: "+str(myebuild)+" not found for "+str(mydo)+"\n")
			return 1

		if debug: # Otherwise it overrides emerge's settings.
			# We have no other way to set debug... debug can't be passed in
			# due to how it's coded... Don't overwrite this so we can use it.
			self._config["PORTAGE_DEBUG"]=str(debug)
	
		self._config["ROOT"]     = myroot
	
		self._config["EBUILD"]   = ebuild_path
		self._config["O"]        = pkg_dir
		self._config["CATEGORY"] = cat
		self._config["FILESDIR"] = pkg_dir+"/files"
		self._config["PF"]       = mypv
		
		self._config["ECLASSDIR"]   = self._config["PORTDIR"]+"/eclass"

		self._config["PROFILE_PATHS"] = PROFILE_PATH+"\n"+CUSTOM_PROFILE_PATH
		self._config["P"]  = mysplit[0]+"-"+mysplit[1]
		self._config["PN"] = mysplit[0]
		self._config["PV"] = mysplit[1]
		self._config["PR"] = mysplit[2]

		# ensure this is set for all phases, setup included.
		# Should be ok again to set $T, as sandbox does not depend on it
		self._config["BUILD_PREFIX"] = self._config["PORTAGE_TMPDIR"]+"/portage"
		self._config["BUILDDIR"]	= self._config["BUILD_PREFIX"]+"/"+self._config["PF"]
		self._config["T"]		= self._config["BUILDDIR"]+"/temp"
		self._config["WORKDIR"] 	= self._config["BUILDDIR"]+"/work"
		self._config["D"]		= self._config["BUILDDIR"]+"/image/"
	

		# bailing now, probably horks a few things up, but neh.
		# got to break a few eggs to make an omelot after all (spelling is wrong, too) :)
		if mydo=="unmerge":
			return 0

		if mydo!="depend":
			try:
				self._config["INHERITED"],self._config["RESTRICT"] = db[root][tree].dbapi.aux_get(
					mycpv,["INHERITED","RESTRICT"])

				self._config["PORTAGE_RESTRICT"]=string.join(flatten(portage_dep.use_reduce(
					portage_dep.paren_reduce(self._config["RESTRICT"]), 
					uselist=self._config["USE"].split() )),' ')

			except SystemExit, e:
				raise
			except Exception, e:
				print "caught exception %s in ebd_proc:doebuild" % str(e)
				self._config["RESTRICT"] = self._config["PORTAGE_RESTRICT"] = ""
				pass
	

		if mysplit[2] == "r0":
			self._config["PVR"]=mysplit[1]
		else:
			self._config["PVR"]=mysplit[1]+"-"+mysplit[2]
	
		self._config["SLOT"]=""
	
		if self._config.has_key("PATH"):
			mysplit=string.split(self._config["PATH"],":")
		else:
			mysplit=[]

		if PORTAGE_BIN_PATH not in mysplit:
			self._config["PATH"]=PORTAGE_BIN_PATH+":"+self._config["PATH"]
	
		if tree=="bintree":
			self._config["BUILD_PREFIX"] += "-pkg"

		self._config["HOME"]         = self._config["BUILD_PREFIX"]+"/homedir"
		self._config["PKG_TMPDIR"]   = self._config["PORTAGE_TMPDIR"]+"/portage-pkg"

		if cleanup and os.path.exists(self._config["BUILDDIR"]):
			print "cleansing builddir"+self._config["BUILDDIR"]
			shutil.rmtree(self._config["BUILDDIR"])

		if mydo=="clean":
			# if clean, just flat out skip the rest of this crap.
			return 0			
	
		self._config["PORTAGE_BASHRC"] = EBUILD_SH_ENV_FILE
	
		#set up KV variable -- DEP SPEEDUP :: Don't waste time. Keep var persistent.

		if mydo not in ["depend","fetch","digest","manifest"]:
			if not self._config.has_key("KV"):
				mykv,err1=ExtractKernelVersion(root+"usr/src/linux")
				if mykv:
					# Regular source tree
					self._config["KV"]=mykv
				else:
					self._config["KV"]=""

			if (mydo!="depend") or not self._config.has_key("KVERS"):
				myso=os.uname()[2]
				self._config["KVERS"]=myso[1]
		
	
		# get possible slot information from the deps file
		if mydo=="depend":
			if self._config.has_key("PORTAGE_DEBUG") and self._config["PORTAGE_DEBUG"]=="1":
				# XXX: This needs to use a FD for saving the output into a file.
				# XXX: Set this up through spawn
				pass
			writemsg("!!! DEBUG: dbkey: %s\n" % str(dbkey),2)
			if dbkey:
				self._config["dbkey"] = dbkey
			else:
				self._config["dbkey"] = self._config.depcachedir+"/aux_db_key_temp"
	
			return 0
			
		self._config["PORTAGE_LOGFILE"]=''
		logfile=None


		#fetch/digest crap
		if mydo not in ["prerm","postrm","preinst","postinst","config","help","setup","unmerge"]:

			newuris, alist = db["/"]["porttree"].dbapi.getfetchlist(mycpv,mysetting=self._config)
			alluris, aalist = db["/"]["porttree"].dbapi.getfetchlist(mycpv,mysettings=self._config,all=1)
			self._config["A"]=string.join(alist," ")
			self._config["AA"]=string.join(aalist," ")
			if ("mirror" in features) or fetchall:
				fetchme=alluris[:]
				checkme=aalist[:]
			elif mydo=="digest":
				fetchme=alluris[:]
				checkme=aalist[:]
				digestfn=self._config["FILESDIR"]+"/digest-"+self._config["PF"]
				if os.path.exists(digestfn):
					mydigests=digestParseFile(digestfn)
					if mydigests:
						for x in mydigests:
							while x in checkme:
								i = checkme.index(x)
								del fetchme[i]
								del checkme[i]
			else:
				fetchme=newuris[:]
				checkme=alist[:]

			try:
				if not os.path.exists(self._config["DISTDIR"]):
					os.makedirs(self._config["DISTDIR"])
				if not os.path.exists(self._config["DISTDIR"]+"/cvs-src"):
					os.makedirs(self._config["DISTDIR"]+"/cvs-src")
			except OSError, e:
				print "!!! File system problem. (Bad Symlink?)"
				print "!!! Fetching may fail:",str(e)

			try:
				mystat=os.stat(self._config["DISTDIR"]+"/cvs-src")
				if ((mystat[stat.ST_GID]!=portage_gid) or ((mystat[stat.ST_MODE]&00775)!=00775)) and not listonly:
					print "*** Adjusting cvs-src permissions for portage user..."
					os.chown(self._config["DISTDIR"]+"/cvs-src",0,portage_gid)
					os.chmod(self._config["DISTDIR"]+"/cvs-src",00775)
					portage_exec.spawn("chgrp -R "+str(portage_gid)+" "+self._config["DISTDIR"]+"/cvs-src")
					portage_exec.spawn("chmod -R g+rw "+self._config["DISTDIR"]+"/cvs-src")
			except (IOError, OSError):
				pass

			if not fetch(fetchme, self._config, listonly=listonly, fetchonly=fetchonly,verbosity=verbosity):
				return 1

			if mydo=="fetch" and listonly:
				return 0

			if "digest" in features:
				#generate digest if it doesn't exist.
				if mydo=="digest":
					# exemption to the return rule
					return (not digestgen(aalist,self._config,overwrite=1,verbosity=verbosity))
				else:
					digestgen(aalist,self._config,overwrite=0,verbosity=verbosity)

			elif mydo=="digest":
				#since we are calling "digest" directly, recreate the digest even if it already exists
				return (not digestgen(checkme,self._config,overwrite=1,verbosity=verbosity))
			if mydo=="manifest":
				return (not digestgen(checkme,self._config,overwrite=1,manifestonly=1,verbosity=verbosity))
	
			if not digestcheck(checkme, self._config, ("strict" in features),verbosity=verbosity):
				return 1
		
			if mydo=="fetch":
				return 0

		if not os.path.exists(self._config["BUILD_PREFIX"]):
			os.makedirs(self._config["BUILD_PREFIX"])
		os.chown(self._config["BUILD_PREFIX"],portage_uid,portage_gid)
		os.chmod(self._config["BUILD_PREFIX"],00775)

		if not os.path.exists(self._config["T"]):
			print "creating temp dir"
			os.makedirs(self._config["T"])
		os.chown(self._config["T"],portage_uid,portage_gid)
		os.chmod(self._config["T"],0770)
	
		logdir = self._config["T"]+"/logging"
		if not os.path.exists(logdir):
			os.makedirs(logdir)
		os.chown(logdir, portage_uid, portage_gid)
		os.chmod(logdir, 0770)
	
		try:
			#XXX: negative restrict
			myrestrict = self._config["PORTAGE_RESTRICT"].split()
			if ("nouserpriv" not in myrestrict and "userpriv" not in myrestrict):
				if ("userpriv" in self._config.features) and (portage_uid and portage_gid):
					if (secpass==2):
						if os.path.exists(self._config["HOME"]):
							# XXX: Potentially bad, but held down by HOME replacement above.
							portage_exec.spawn("rm -Rf "+self._config["HOME"])
						if not os.path.exists(self._config["HOME"]):
							os.makedirs(self._config["HOME"])
				elif ("userpriv" in features):
					print "!!! Disabling userpriv from features... Portage UID/GID not valid."
					del features[features.index("userpriv")]
		except (IOError, OSError), e:
			print "!!! Couldn't empty HOME:",self._config["HOME"]
			print "!!!",e

			
		try:
			# no reason to check for depend since depend returns above.
			if not os.path.exists(self._config["BUILD_PREFIX"]):
				os.makedirs(self._config["BUILD_PREFIX"])
			os.chown(self._config["BUILD_PREFIX"],portage_uid,portage_gid)
			if not os.path.exists(self._config["BUILDDIR"]):
				os.makedirs(self._config["BUILDDIR"])
			os.chown(self._config["BUILDDIR"],portage_uid,portage_gid)

	
		except OSError, e:
			print "!!! File system problem. (ReadOnly? Out of space?)"
			print "!!! Perhaps: rm -Rf",self._config["BUILD_PREFIX"]
			print "!!!",str(e)
			return 1
	
		try:
			if not os.path.exists(self._config["HOME"]):
				os.makedirs(self._config["HOME"])
			os.chown(self._config["HOME"],portage_uid,portage_gid)
			os.chmod(self._config["HOME"],02770)

		except OSError, e:
			print "!!! File system problem. (ReadOnly? Out of space?)"
			print "!!! Failed to create fake home directory in BUILDDIR"
			print "!!!",str(e)
			return 1

		try:
			if ("userpriv" in features) and ("ccache" in features):
				if (not self._config.has_key("CCACHE_DIR")) or (self._config["CCACHE_DIR"]==""):
					self._config["CCACHE_DIR"]=self._config["PORTAGE_TMPDIR"]+"/ccache"
				if not os.path.exists(self._config["CCACHE_DIR"]):
					os.makedirs(self._config["CCACHE_DIR"])
				os.chown(self._config["CCACHE_DIR"],portage_uid,portage_gid)
				os.chmod(self._config["CCACHE_DIR"],0775)
		except OSError, e:
			print "!!! File system problem. (ReadOnly? Out of space?)"
			print "!!! Perhaps: rm -Rf",self._config["BUILD_PREFIX"]
			print "!!!",str(e)
			return 1

		try:
			mystat=os.stat(self._config["CCACHE_DIR"])
			if (mystat[stat.ST_GID]!=portage_gid) or ((mystat[stat.ST_MODE]&02070)!=02070):
				print "*** Adjusting ccache permissions for portage user..."
				os.chown(self._config["CCACHE_DIR"],portage_uid,portage_gid)
				os.chmod(self._config["CCACHE_DIR"],02770)
				portage_exec.spawn("chown -R "+str(portage_uid)+":"+str(portage_gid)+" "+self._config["CCACHE_DIR"])
				portage_exec.spawn("chmod -R g+rw "+self._config["CCACHE_DIR"])
		except (OSError, IOError):
			pass
				
		if "distcc" in features:
			try:
				if (not self._config.has_key("DISTCC_DIR")) or (self._config["DISTCC_DIR"]==""):
					self._config["DISTCC_DIR"]=self._config["PORTAGE_TMPDIR"]+"/portage/.distcc"
				if not os.path.exists(self._config["DISTCC_DIR"]):
					os.makedirs(self._config["DISTCC_DIR"])
					os.chown(self._config["DISTCC_DIR"],portage_uid,portage_gid)
					os.chmod(self._config["DISTCC_DIR"],02775)
				for x in ("/lock", "/state"):
					if not os.path.exists(self._config["DISTCC_DIR"]+x):
						os.mkdir(self._config["DISTCC_DIR"]+x)
						os.chown(self._config["DISTCC_DIR"]+x,portage_uid,portage_gid)
						os.chmod(self._config["DISTCC_DIR"]+x,02775)
			except OSError, e:
				writemsg("\n!!! File system problem when setting DISTCC_DIR directory permissions.\n")
				writemsg(  "!!! DISTCC_DIR="+str(self._config["DISTCC_DIR"]+"\n"))
				writemsg(  "!!! "+str(e)+"\n\n")
				time.sleep(5)
				features.remove("distcc")
				self._config["DISTCC_DIR"]=""

		# break off into process_phase
		if self._config.has_key("PORT_LOGDIR"):
			try:
				st=os.stat(self._config["PORT_LOGDIR"])
				if not st.st_gid == portage_gid:
					os.chown(self._config["PORT_LOGDIR"], -1, portage_gid)
				if not st.st_mode & (os.W_OK << 3):
					os.chmod(self._config["PORT_LOGDIR"], st.st_mode | (os.W_OK << 3))
				# by this time, we have write access to the logdir.  or it's bailed.
				try:
					os.chown(self._config["BUILD_PREFIX"],portage_uid,portage_gid)
					os.chmod(self._config["PORT_LOGDIR"],00770)
					if not self._config.has_key("LOG_PF") or (self._config["LOG_PF"] != self._config["PF"]):
						self._config["LOG_PF"]=self._config["PF"]
						self._config["LOG_COUNTER"]=str(db[myroot]["vartree"].dbapi.get_counter_tick_core("/"))
					self._config["PORTAGE_LOGFILE"]="%s/%s-%s.log" % (self._config["PORT_LOGDIR"],self._config["LOG_COUNTER"],self._config["LOG_PF"])
					if os.path.exists(self._config["PORTAGE_LOGFILE"]):
						os.chmod(self._config["PORTAGE_LOGFILE"], 0664)
						os.chown(self._config["PORTAGE_LOGFILE"], -1,portage_gid)
				except ValueError, e:
					self._config["PORT_LOGDIR"]=""
					print "!!! Unable to chown/chmod PORT_LOGDIR. Disabling logging."
					print "!!!",e
			except (OSError, IOError):
				print "!!! Cannot create log... No write access / Does not exist"
				print "!!! PORT_LOGDIR:",self._config["PORT_LOGDIR"]
				self._config["PORT_LOGDIR"]=""

		# if any of these are being called, handle them -- running them out of the sandbox -- and stop now.
		if mydo in ["help","setup"]:
			return 0
#			return spawn(EBUILD_SH_BINARY+" "+mydo,self._config,debug=debug,free=1,logfile=logfile)
		elif mydo in ["prerm","postrm","preinst","postinst","config"]:
			self._config.load_infodir(pkg_dir)
			if not use_info_env:
				print "overloading port_env_file setting to %s" % self._config["T"]+"/environment"
				self._config["PORT_ENV_FILE"] = self._config["T"] + "/environment"
				if not os.path.exists(self._config["PORT_ENV_FILE"]):
					from output import red
					print red("!!!")+" err.. it doesn't exist.  that's bad."
					sys.exit(1)
			return 0
#			return spawn(EBUILD_SH_BINARY+" "+mydo,self._config,debug=debug,free=1,logfile=logfile)
	
		try: 
			self._config["SLOT"], self._config["RESTRICT"] = db["/"]["porttree"].dbapi.aux_get(mycpv,["SLOT","RESTRICT"])
		except (IOError,KeyError):
			print red("doebuild():")+" aux_get() error reading "+mycpv+"; aborting."
			sys.exit(1)

		#initial dep checks complete; time to process main commands
	
		nosandbox=(("userpriv" in features) and ("usersandbox" not in features))
		actionmap={
				  "depend": {                 "args":(0,1)},         # sandbox  / portage
				  "setup":  {                 "args":(1,0)},         # without  / root
				 "unpack":  {"dep":"setup",   "args":(0,1)},         # sandbox  / portage
				"compile":  {"dep":"unpack",  "args":(nosandbox,1)}, # optional / portage
				   "test":  {"dep":"compile", "args":(nosandbox,1)}, # optional / portage
				"install":  {"dep":"test",    "args":(0,0)},         # sandbox  / root
				    "rpm":  {"dep":"install", "args":(0,0)},         # sandbox  / root
    				"package":  {"dep":"install", "args":(0,0)},         # sandbox  / root
		}
	
		if mydo in actionmap.keys():	
			if mydo=="package":
				for x in ["","/"+self._config["CATEGORY"],"/All"]:
					if not os.path.exists(self._config["PKGDIR"]+x):
						os.makedirs(self._config["PKGDIR"]+x)
			# REBUILD CODE FOR TBZ2 --- XXXX
			return 0
#			return spawnebuild(mydo,actionmap,self._config,debug,logfile=logfile)
		elif mydo=="qmerge": 
			#check to ensure install was run.  this *only* pops up when users forget it and are using ebuild
			bail=False
			if not os.path.exists(self._config["BUILDDIR"]+"/.completed_stages"):
				bail=True
			else:
				myf=open(self._config["BUILDDIR"]+"/.completed_stages")
				myd=myf.readlines()
				myf.close()
				if len(myd) == 0:
					bail = True
				else:
					bail = ("install" not in myd[0].split())
			if bail:
				print "!!! mydo=qmerge, but install phase hasn't been ran"
				sys.exit(1)

			#qmerge is specifically not supposed to do a runtime dep check
			return 0
#			return merge(self._config["CATEGORY"],self._config["PF"],self._config["D"],self._config["BUILDDIR"]+"/build-info",myroot,self._config)
		elif mydo=="merge":
			return 0
#			retval=spawnebuild("install",actionmap,self._config,debug,alwaysdep=1,logfile=logfile)
			if retval:
				return retval

#			return merge(self._config["CATEGORY"],self._config["PF"],self._config["D"],self._config["BUILDDIR"]+"/build-info",myroot,self._config,myebuild=self._config["EBUILD"])
		else:
			print "!!! Unknown mydo:",mydo
			sys.exit(1)

	# phases
	# my... god... this... is... ugly.
	# we're talking red headed step child of medusa ugly here.

	def process_phase(self,phase,myebuild,myroot,allstages=False,**keywords):
		"""the public 'doebuild' interface- all phases are called here, along w/ a valid config
		allstages is the equivalent of 'do merge, and all needed phases to get to it'
		**keywords is options passed on to __adjust_env.  It will be removed as __adjust_env is digested"""
		from portage import merge,unmerge,features

		validcommands = ["help","clean","prerm","postrm","preinst","postinst",
		                "config","setup","depend","fetch","digest",
		                "unpack","compile","test","install","rpm","qmerge","merge",
		                "package","unmerge", "manifest"]
	
		if phase not in validcommands:
			validcommands.sort()
			writemsg("!!! doebuild: '%s' is not one of the following valid commands:" % phase)
			for vcount in range(len(validcommands)):
				if vcount%6 == 0:
					writemsg("\n!!! ")
				writemsg(string.ljust(validcommands[vcount], 11))
			writemsg("\n")
			return 1

		retval=self.__adjust_env(phase,myebuild,myroot,**keywords)
		if retval:
			return retval

		if "userpriv" in features:
			sandbox = ("usersandbox" in features)
		else:
			sandbox = ("sandbox" in features)

	        droppriv=(("userpriv" in features) and \
	                ("nouserpriv" not in string.split(self._config["PORTAGE_RESTRICT"])) and portage_exec.userpriv_capable)
		use_fakeroot=(("userpriv_fakeroot" in features) and droppriv and portage_exec.fakeroot_capable)

		# basically a nasty graph of 'w/ this phase, have it userprived/sandboxed/fakeroot', and run
		# these phases prior
		actionmap={
			  "depend": {                "sandbox":False,	"userpriv":True, "fakeroot":False},
			  "setup":  {                "sandbox":True,	"userpriv":False, "fakeroot":False},
			 "unpack":  {"dep":"setup",  "sandbox":sandbox,	"userpriv":True, "fakeroot":False},
			"compile":  {"dep":"unpack", "sandbox":sandbox,"userpriv":True, "fakeroot":False},
			   "test":  {"dep":"compile","sandbox":sandbox,"userpriv":True, "fakeroot":False},
			"install":  {"dep":"test",   "sandbox":(not use_fakeroot or (not use_fakeroot and sandbox)),
									"userpriv":use_fakeroot,"fakeroot":use_fakeroot},
			    "rpm":  {"dep":"install","sandbox":False,	"userpriv":use_fakeroot, "fakeroot":use_fakeroot},
	    		"package":  {"dep":"install", "sandbox":False,	"userpriv":use_fakeroot, "fakeroot":use_fakeroot},
			"merge"	 :  {"dep":"install", "sandbox":True,	"userpriv":False, "fakeroot":False}
		}

		merging=False
		# this shouldn't technically ever be called, get_keys exists for this.
		# left in for compatability while portage.doebuild still exists
		if phase=="depend":
			return retval
		elif phase=="unmerge":
			return unmerge(self._config["CATEGORY"],self._config["PF"],myroot,self._config)
		elif phase in ["fetch","digest","manifest","clean"]:
			return retval
		elif phase=="merge":
			merging=True
		elif phase=="qmerge":
			#no phases ran.
			phase="merge"
			merging=True
#			return merge(self._config["CATEGORY"],self._config["PF"],self._config["D"],self._config["BUILDDIR"]+"/build-info",myroot,\
#				self._config)

		elif phase in ["help","clean","prerm","postrm","preinst","postinst","config"]:
			self.__ebp = request_ebuild_processor(self._config, userpriv=False)
			self.__ebp.write("process_ebuild %s" % phase)
			self.__ebp.send_env(self._config)
			self.__ebp.set_sandbox_state(phase in ["help","clean"])
			self.__ebp.write("start_processing")
			retval = self.__generic_phase([],self._config)
			release_ebuild_processor(self.__ebp)
			self.__ebp = None
			return not retval

		k=phase
		# represent the phases to run, grouping each phase based upon if it's sandboxed, fakerooted, and userpriv'd
		# ugly at a glance, but remember a processor can run multiple phases now.
		# best to not be wasteful in terms of env saving/restoring, and just run all applicable phases in one shot
		phases=[[[phase]]]
		sandboxed=[[actionmap[phase]["sandbox"]]]
		privs=[(actionmap[phase]["userpriv"],actionmap[phase]["fakeroot"])]

		if allstages:
			while actionmap[k].has_key("dep"):
				k=actionmap[k]["dep"]
				if actionmap[k]["userpriv"] != privs[-1][0] or actionmap[k]["fakeroot"] != privs[-1][1]:
					phases.append([[k]])
					sandboxed.append([actionmap[k]["sandbox"]])
					privs.append((actionmap[k]["userpriv"],actionmap[k]["fakeroot"]))
				elif actionmap[k]["sandbox"] != sandboxed[-1][-1]:
					phases[-1].append([k])
					sandboxed[-1].extend([actionmap[k]["sandbox"]])
				else:
					phases[-1][-1].append(k)
			privs.reverse()
			phases.reverse()
			sandboxed.reverse()
			for x in phases:
				for y in x:
					y.reverse()
				x.reverse()
		# and now we have our phases grouped in parallel to the sandbox/userpriv/fakeroot state.

		all_phases = portage_util.flatten(phases)

#		print "all_phases=",all_phases
#		print "phases=",phases
#		print "sandbox=",sandboxed
#		print "privs=",privs
#		sys.exit(1)
#		print "\n\ndroppriv=",droppriv,"use_fakeroot=",use_fakeroot,"\n\n"

		#temporary hack until sandbox + fakeroot (if ever) play nice.
		while privs:
			if self.__ebp == None or (droppriv and self.__ebp.userprived() != privs[0][0]) or \
				(use_fakeroot and self.__ebp.fakerooted() != privs[0][1]):
				if self.__ebp != None:
					print "swapping processors for",phases[0][0]
					release_ebuild_processor(self.__ebp)
					self.__ebp = None
				opts={}

				#only engage fakeroot when userpriv'd
				if use_fakeroot and privs[0][1]:
					opts["save_file"] = self._config["T"]+"/fakeroot_db"

				self.__ebp = request_ebuild_processor(self._config, userpriv=(privs[0][0] and droppriv), \
					fakeroot=(privs[0][1] and use_fakeroot), \

				sandbox=(not (privs[0][1] and use_fakeroot) and portage_exec.sandbox_capable),**opts)

			#loop through the instances where the processor must have the same sandboxed state-
			#note a sandbox'd process can have it's sandbox disabled.
			#this seperation is needed since you can't mix sandbox and fakeroot atm.
			for sandbox in sandboxed[0]:
				if "merge" in phases[0][0]:
					if len(phases[0][0]) == 1:
						print "skipping this phase, it's just merge"
						continue
					phases[0][0].remove("merge")

				self.__ebp.write("process_ebuild %s" % string.join(phases[0][0]," "))
				self.__ebp.send_env(self._config)
				self.__ebp.set_sandbox_state(sandbox)
				self.__ebp.write("start_processing")
				phases[0].pop(0)
				retval = not self.__generic_phase([],self._config)
				if retval:
					release_ebuild_processor(self.__ebp)
					self.__ebp = None
					return retval
			sandboxed.pop(0)
			privs.pop(0)
			phases.pop(0)
		# hey hey. we're done.  Now give it back.
		release_ebuild_processor(self.__ebp)
		self.__ebp = None

		# packaging moved out of ebuild.sh, and into this code.
		# makes it so ebuild.sh no longer must run as root for the package phase.
		if "package" in all_phases:
			print "processing package"
			#mv "${PF}.tbz2" "${PKGDIR}/All" 
			if not os.path.exists(self._config["PKGDIR"]+"/All"):
				os.makedirs(self._config["PKGDIR"]+"/All")
			if not os.path.exists(self._config["PKGDIR"]+"/"+self._config["CATEGORY"]):
				os.makedirs(self._config["PKGDIR"]+"/"+self._config["CATEGORY"])
			if os.path.exists("%s/All/%s.tbz2" % (self._config["PKGDIR"],self._config["PF"])):
				os.remove("%s/All/%s.tbz2" % (self._config["PKGDIR"],self._config["PF"]))
			retval = not portage_util.movefile("%s/%s.tbz2" % (self._config["BUILDDIR"],self._config["PF"]),
				self._config["PKGDIR"]+"/All/"+self._config["PF"]+".tbz2") > 0
			if retval:	return False
			if os.path.exists("%s/%s/%s.tbz2" % (self._config["PKGDIR"],self._config["CATEGORY"],self._config["PF"])):
				os.remove("%s/%s/%s.tbz2" % (self._config["PKGDIR"],self._config["CATEGORY"],self._config["PF"]))
			os.symlink("%s/All/%s.tbz2" % (self._config["PKGDIR"],self._config["PF"]),
				"%s/%s/%s.tbz2" % (self._config["PKGDIR"],self._config["CATEGORY"],self._config["PF"]))

		#same as the package phase above, removes the root requirement for the rpm phase.
		if "rpm" in all_phases:
			rpm_name="%s-%s-%s" % (self._config["PN"],self._config["PV"],self._config["PR"])

			retval = not portage_util.movefile("%s/%s.tar.gz" % (self._config["T"],self._config["PF"]),
				"/usr/src/redhat/SOURCES/%s.tar.gz" % self._config["PF"]) > 0
			if retval:
				print "moving src for rpm failed, retval=",retval
				return False

			retval=portage_exec.spawn(("rpmbuild","-bb","%s/%s.spec" % \
				(self._config["BUILDDIR"],self._config["PF"])))
			if retval:
				print "Failed to integrate rpm spec file"
				return retval

			if not os.path.exists(self._config["RPMDIR"]+"/"+self._config["CATEGORY"]):
				os.makedirs(self._config["RPMDIR"]+"/"+self._config["CATEGORY"])

			retval = not portage_util.movefile("/usr/src/redhat/RPMS/i386/%s.i386.rpm" % rpm_name,
				"%s/%s/%s.rpm" % (self._config["RPMDIR"],self._config["CATEGORY"],rpm_name)) > 0
			if retval:
				print "rpm failed"
				return retval


		# not great check, but it works.
		# basically, if FEATURES="-buildpkg" emerge package was called, the files in the current 
		# image directory don't have their actual perms.  so we use an ugly bit of bash
		# to make the fakeroot (claimed) permissions/owners a reality.
		if use_fakeroot and os.path.exists(self._config["T"]+"/fakeroot_db") and merging:
			print "correcting fakeroot privs"
			retval=portage_exec.spawn(("/usr/lib/portage/bin/affect-fakeroot-perms.sh", \
				self._config["T"]+"/fakeroot_db", \
				self._config["D"]),env={"BASHRC":portage_const.INVALID_ENV_FILE})
			if retval or retval == None:
				print red("!!!")+"affecting fakeroot perms after the fact failed"
				return retval

		if merging:
			print "processing merge"
			retval = merge(self._config["CATEGORY"],self._config["PF"],self._config["D"],self._config["BUILDDIR"]+"/build-info",myroot,\
				self._config,myebuild=self._config["EBUILD"])
		return retval

	# this basically handles all hijacks from the daemon, whether confcache or portageq.
	def __generic_phase(self,breakers,interpret_results=True):
		"""internal function that responds to the running ebuild processor's requests
		this enables portageq hijack, sandbox summaries, confcache among other things
		interpret_results controls whether this returns true/false, or the string the 
		processor spoke that caused this to release control
		breaks is list of strings that cause this loop/interpretter to relinquish control"""
		b = breakers[:]
		b.extend(["prob","phases failed","phases succeeded","env_receiving_failed"])
		line=''
		while line not in b:
			line=self.__ebp.read()
			line=line[:-1]

			if line[0:23] == "request_sandbox_summary":
				self.__ebp.sandbox_summary(line[24:])
			elif line[0:17] == "request_confcache":
				self.load_confcache(line[18:])
			elif line[0:16] == "update_confcache":
				k=line[17:].split()
				# sandbox_debug_log, local_cache
				self.update_confcache(self._config,k[0],k[1])
			elif line[0:8] == "portageq":
				keys=line[8:].split()
				try:
					e,s=getattr(self.portageq,keys[0])(keys[1:])
				except SystemExit, e:
					raise
				except Exception, ex:
					sys.stderr.write("caught exception %s\n" % str(ex))
					e=2
					s="ERROR: insufficient paramters!"
				self.__ebp.write("return_code="+str(e))
				if len(s):
					self.__ebp.write(s)
				self.__ebp.write("stop_text")
		self.processed += 1
		if interpret_results:
			return (line=="phases succeeded")
		return line

