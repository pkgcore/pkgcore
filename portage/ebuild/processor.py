# Copyright: 2004-2005 Gentoo Foundation
# License: GPL2
# $Id: processor.py 2288 2005-11-10 03:39:28Z ferringb $

# this needs work.  it's been pruned heavily from what ebd used originally, but it still isn't what 
# I would define as 'right'

inactive_ebp_list = []
active_ebp_list = []

import portage.spawn, os, logging
from portage.util.currying import post_curry
from portage.const import depends_phase_path, EBUILD_DAEMON_PATH, PORTAGE_BIN_PATH


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


def request_ebuild_processor(userpriv=False, sandbox=None, fakeroot=False, save_file=None):
	"""request an ebuild_processor instance from the pool, or create a new one
	  this walks through the requirements, matching a inactive processor if one exists
	  note fakerooted processors are never reused, do to the nature of fakeroot"""

	if sandbox == None:
		sandbox = portage.spawn.sandbox_capable

	global inactive_ebp_list, active_ebp_list
	if not fakeroot:
		for x in inactive_ebp_list:
			if x.userprived() == userpriv and (x.sandboxed() or not sandbox):
				if not x.is_alive():
					inactive_ebp_list.remove(x)
					continue
				inactive_ebp_list.remove(x)
				active_ebp_list.append(x)
				return x
	e=ebuild_processor(userpriv, sandbox, fakeroot, save_file)
	active_ebp_list.append(e)
	return e


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
	def __init__(self, userpriv, sandbox, fakeroot, save_file):
		"""
		sandbox enables a sandboxed processor
		userpriv enables a userpriv'd processor
		fakeroot enables a fakeroot'd processor- this is a mutually exclusive option to sandbox, and 
		requires userpriv to be enabled.  
		
		Violating this will result in nastyness
		"""

		self.ebd = EBUILD_DAEMON_PATH
		self.ebd_libs = PORTAGE_BIN_PATH
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
			if portage.spawn.userpriv_capable:
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
			spawn_func = portage.spawn.spawn_sandbox
#			env.update({"SANDBOX_DEBUG":"1","SANDBOX_DEBUG_LOG":"/var/tmp/test"})

		elif fakeroot:
			self.__fakeroot = True
			spawn_func = portage.spawn.spawn_fakeroot
			args.append(save_file)
		else:
			spawn_func = portage.spawn.spawn

		self.pid = spawn_func(self.ebd+" daemonize", fd_pipes={0:0, 1:1, 2:2, 3:cread, 4:dwrite},
			returnpid=True, env=env, *args, **spawn_opts)[0]

		os.close(cread)
		os.close(dwrite)
		self.ebd_write = os.fdopen(cwrite,"w")
		self.ebd_read  = os.fdopen(dread,"r")

		# basically a quick "yo" to the daemon
		self.write("dude?")
		if not self.expect("dude!"):
			print "error in server coms, bailing."
			raise Exception("expected 'dude!' response from ebd, which wasn't received. likely a bug")
		self.write(PORTAGE_BIN_PATH)
		if self.__sandbox:
			self.write("sandbox_log?")
			self.__sandbox_log = self.read().split()[0]
		self.dont_export_vars=self.read().split()
		# locking isn't used much, but w/ threading this will matter


	def prep_phase(self, phase, env, sandbox=None, logging=None):
		"""
		Utility function, combines multiple calls into one, leaving the processor in a state where all that 
		remains is a call start_processing call, then generic_handler event loop.
		
		Returns True for success, false for everything else.
		"""
		
		self.write("process_ebuild %s" % phase)
		if not self.send_env(env):
			return False
		if sandbox:
			self.set_sandbox_state(sandbox)
		if logging:
			self.set_logging(logging)
		return True

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
		return self.pid > None


	def shutdown_processor(self):
		"""tell the daemon to shut itself down, and mark this instance as dead"""
		try:
			if self.is_alive():
				self.write("shutdown_daemon")
				self.ebd_write.close()
				self.ebd_read.close()

				# now we wait.
				os.waitpid(self.pid, 0)

		except (IOError,OSError):
			pass

		# currently, this assumes all went well.
		# which isn't always true.
		self.pid = None


	def set_sandbox_state(self,state):
		"""tell the daemon whether to enable the sandbox, or disable it"""
		if state:
			self.write("set_sandbox_state 1")
		else:
			self.write("set_sandbox_state 0")


	def send_env(self, env_dict):
		"""transfer the ebuild's desired env (env_dict) to the running daemon"""

		self.write("start_receiving_env\n")
		exported_keys = ''
		for x in env_dict.keys():
			if x not in self.dont_export_vars:
				if not x[0].isalpha():
					raise KeyError(x)
				s=env_dict[x].replace("\\","\\\\\\\\")
				s=s.replace("'","\\\\'")
				s=s.replace("\n","\\\n")
				self.write("%s='%s'\n" % (x, s), flush=False)
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
		if self.is_alive():
			# I'd love to know why the exception wrapping is required...
			try:
				self.shutdown_processor()
			except TypeError:
				pass


	def get_keys(self, package_inst, eclass_cache):
		"""request the auxdbkeys from an ebuild
		returns a dict when successful, None when failed"""

		self.write("process_ebuild depend")
		e = expected_ebuild_env(package_inst)
		e["PATH"] = depends_phase_path
		self.send_env(expected_ebuild_env(package_inst))
		self.set_sandbox_state(True)
		self.write("start_processing")

		metadata_keys = {}
		val=self.generic_handler(additional_commands={ \
			"request_inherit":post_curry(self.__class__._inherit, eclass_cache), \
			"key":post_curry(self.__class__._receive_key, metadata_keys) } )

		if not val:
			logging.error("returned val from get_keys was '%s'" % str(val))
			raise Exception(val)

		return metadata_keys


	def _receive_key(self, line, keys_dict):
		line=line.split("=",1)
		l=len(line)
		if l != 2:
			raise FinishedProcessing(True)
		else:
			keys_dict[line[0]] = line[1]
		

	def _inherit(self, line, ecache):
		"""callback for implementing inherit digging into eclass_cache.  not for normal consumption."""
		if line == None:
			self.write("failed")
			raise UnhandledCommand("inherit requires an eclass specified, none specified")
		
		line=line.strip()
		if ecache.get_eclass_path != None:
			value = ecache.get_eclass_path(line)
			self.write("path")
			self.write(value)
		elif ecache.get_eclass_data != None:
			value = ecache.get_eclass_data(line)
			self.write("transfer")
			self.write(value)
		else:
			raise AttributeError("neither get_data nor get_path is usable on ecache!")
		

	# this basically handles all hijacks from the daemon, whether confcache or portageq.
	def generic_handler(self, additional_commands=None):
		"""internal function that responds to the running ebuild processor's requests
		
		additional_commands is a dict of command:callable.  If you need to slip in extra args, look into portage.util.currying.

		commands names cannot have spaces.  the callable is called with the processor as first arg, and 
		remaining string (None if no remaining fragment) as second arg.
		If you need to split the args to command, whitespace splitting falls to your func.
		
		Chucks an UnhandledCommand exception when an unknown command is encountered.
		"""

		# note that self is passed in.  so... we just pass in the unbound instance.  Specifically, via digging through __class__
		# if you don't do it, sandbox_summary (fex) cannot be overriden, this func will just use this classes version.
		# so dig through self.__class__ for it. :P

		handlers = {"request_sandbox_summary":(self.__class__.sandbox_summary,[],{})}
		f = post_curry(chuck_UnhandledCommand, False)
		for x in ("prob", "env_receiving_failed"):
			handlers[x] = f
		del f

		handlers["phases"] = post_curry(chuck_StoppingCommand, lambda f: f.lower().strip()=="succeeded")

		if additional_commands is not None:
			for x in additional_commands.keys():
				if not callable(additional_commands[x]):
					raise TypeError(additional_commands[x])

			handlers.update(additional_commands)

		try:
			while True:
				line=self.read().strip()
				# split on first whitespace.
				s=line.split(None,1)
				if s[0] in handlers:
					if len(s) == 1:
						s.append(None)
					handlers[s[0]](self, s[1])
				else:
					logging.error("unhandled command '%s', line '%s'" % (s[0], line))
					raise UnhandledCommand(line)

		except FinishedProcessing, fp:
			v = fp.val; del fp
			return v


def chuck_UnhandledCommand(processor, line):
	raise UnhandledCommand(line)

def chuck_StoppingCommand(processor, val, *args):
	if callable(val):
		raise FinishedProcessing(val, args[0])
	raise FinishedProcessing(val)

class ProcessingInterruption(Exception):
	pass

class FinishedProcessing(ProcessingInterruption):
	def __init__(self, val, msg=None):	self.val, self.msg = val, msg
	def __str__(self):	return "Finished processing with val, %s" % str(self.val)

class UnhandledCommand(ProcessingInterruption):
	def __init__(self, line=None):		self.line=line
	def __str__(self):						return "unhandled command, %s" % self.line

__all__ = ("request_ebuild_processor", "release_ebuild_processor", "ebuild_processor"
	"UnhandledCommand", "expected_ebuild_env")

def expected_ebuild_env(pkg, d=None):
	if d is None:
		d = {}
	d["CATEGORY"] = pkg.category
	d["PF"] = "-".join((pkg.package, pkg.fullver))
	d["P"]  = "-".join((pkg.package, pkg.version))
	d["PN"] = pkg.package
	d["PV"] = pkg.version
	if pkg.revision != None:
		d["PR"] = "-r" + str(pkg.revision)
	else:
		d["PR"] = ""
	d["PVR"]= pkg.fullver
	d["EBUILD"] = pkg.path

	return d

