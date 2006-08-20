# Copyright: 2004-2006 Brian Harring <ferringb@gmail.com>
# License: GPL2


"""
low level ebuild processor.

This basically is a coprocessor that controls a bash daemon for actual ebuild execution.
Via this, the bash side can reach into the python side (and vice versa), enabling remote trees (piping 
data from python side into bash side for example).

A couple of processors are left lingering while pkgcore is running for the purpose of avoiding spawning
overhead, this (and the general design) reduces regen time by over 40% compared to portage-2.1
"""

# this needs work.  it's been pruned heavily from what ebd used originally, but it still isn't what
# I would define as 'right'


__all__ = ("request_ebuild_processor", "release_ebuild_processor", "EbuildProcessor"
	"UnhandledCommand", "expected_ebuild_env")


inactive_ebp_list = []
active_ebp_list = []

import pkgcore.spawn, os
from pkgcore.util.currying import post_curry, pre_curry
from pkgcore.const import depends_phase_path, EBUILD_DAEMON_PATH, EBUILD_ENV_PATH, EBD_ENV_PATH
from pkgcore.util.demandload import demandload
from pkgcore.os_data import portage_uid, portage_gid
demandload(globals(), "logging")


def shutdown_all_processors():
	"""kill off all known processors"""
	global active_ebp_list, inactive_ebp_list

	while active_ebp_list:
		try:
			active_ebp_list.pop().shutdown_processor()
		except (IOError, OSError):
			pass

	while inactive_ebp_list:
		try:
			inactive_ebp_list.pop().shutdown_processor()
		except (IOError, OSError):
			pass

pkgcore.spawn.atexit_register(shutdown_all_processors)

def request_ebuild_processor(userpriv=False, sandbox=None, fakeroot=False, save_file=None):
	"""
	request an ebuild_processor instance from the pool, creating a new one if needed
	
	Note that fakeroot processes are B{never} reused due to the fact the fakeroot env becomes localized to the pkg
	it's handling.
	
	@return: L{EbuildProcessor}
	@param userpriv: should the processor be deprived to L{pkgcore.os_data.portage_gid} and L{pkgcore.os_data.portage_uid}?
	@param sandbox: should the processor be sandboxed?
	@param fakeroot: should the processor be fakerooted?  This option is mutually exclusive to sandbox, and requires
	save_file to be set
	@param save_file: location to store fakeroot state dumps
	"""

	if sandbox is None:
		sandbox = pkgcore.spawn.sandbox_capable

	global inactive_ebp_list, active_ebp_list
	if not fakeroot:
		for x in inactive_ebp_list:
			if x.userprived() == userpriv and (x.sandboxed() or not sandbox):
				if not x.is_alive:
					inactive_ebp_list.remove(x)
					continue
				inactive_ebp_list.remove(x)
				active_ebp_list.append(x)
				return x
	e = EbuildProcessor(userpriv, sandbox, fakeroot, save_file)
	active_ebp_list.append(e)
	return e


def release_ebuild_processor(ebp):
	"""
	the inverse of request_ebuild_processor.  
	
	Any processor requested via request_ebuild_processor B{must} be released via this function once it's no longer in use.
	This includes fakerooted processors.

	@param ebp: L{EbuildProcessor} instance
	@return: boolean indicating release results- if the processor isn't known as active, False is returned.
	If a processor isn't known as active, this means either calling error or an internal error
	"""
	
	global inactive_ebp_list, active_ebp_list
	try:
		active_ebp_list.remove(ebp)
	except ValueError:
		return False

	try:
		inactive_ebp_list.index(ebp)
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


class EbuildProcessor:

	"""abstraction of a running ebuild.sh instance- the env, functions, etc that ebuilds expect."""

	def __init__(self, userpriv, sandbox, fakeroot, save_file):
		"""
		@param sandbox: enables a sandboxed processor
		@param userpriv: enables a userpriv'd processor
		@param fakeroot: enables a fakeroot'd processor- this is a mutually exclusive option to sandbox, and
		requires userpriv to be enabled. Violating this will result in nastyness
		"""

		self.ebd = EBUILD_DAEMON_PATH
		spawn_opts = {}

		if fakeroot and (sandbox or not userpriv):
			import traceback
			traceback.print_stack()
			print "warning, was asking to enable fakeroot but-"
			print "sandbox", sandbox, "userpriv", userpriv
			print "this isn't valid.  bailing"
			raise Exception, "cannot initialize with sandbox and fakeroot"

		if userpriv:
			self.__userpriv = True
			spawn_opts.update({"uid":portage_uid, "gid":portage_gid, "groups":[portage_gid], "umask":002})
		else:
			if pkgcore.spawn.userpriv_capable:
				spawn_opts.update({"gid":portage_gid, "groups":[0, portage_gid]})
			self.__userpriv = False

		# open the pipes to be used for chatting with the new daemon
		cread, cwrite = os.pipe()
		dread, dwrite = os.pipe()
		self.__sandbox = False
		self.__fakeroot = False

		# since it's questionable which spawn method we'll use (if sandbox or fakeroot fex),
		# we ensure the bashrc is invalid.
		env = dict((x, "/etc/portage/spork/not/valid/ha/ha") for x in ("BASHRC", "BASH_ENV"))
		args = []
		if sandbox:
			if fakeroot:
				print "!!! ERROR: fakeroot was on, but sandbox was also on"
				sys.exit(1)
			self.__sandbox = True
			spawn_func = pkgcore.spawn.spawn_sandbox
#			env.update({"SANDBOX_DEBUG":"1", "SANDBOX_DEBUG_LOG":"/var/tmp/test"})

		elif fakeroot:
			self.__fakeroot = True
			spawn_func = pkgcore.spawn.spawn_fakeroot
			args.append(save_file)
		else:
			spawn_func = pkgcore.spawn.spawn

		# little trick.  we force the pipes to be high up fd wise so nobody stupidly hits 'em.
		max_fd = min(pkgcore.spawn.max_fd_limit, 1024)
		env.update({"EBD_READ_FD": str(max_fd -2), "EBD_WRITE_FD": str(max_fd -1)})
		self.pid = spawn_func("/bin/bash %s daemonize" % self.ebd, \
			fd_pipes={0:0, 1:1, 2:2, max_fd-2:cread, max_fd-1:dwrite}, \
			returnpid=True, env=env, *args, **spawn_opts)[0]

		os.close(cread)
		os.close(dwrite)
		self.ebd_write = os.fdopen(cwrite, "w")
		self.ebd_read  = os.fdopen(dread, "r")

		# basically a quick "yo" to the daemon
		self.write("dude?")
		if not self.expect("dude!"):
			print "error in server coms, bailing."
			raise Exception("expected 'dude!' response from ebd, which wasn't received. likely a bug")
		self.write(EBD_ENV_PATH)
		if self.__sandbox:
			self.write("sandbox_log?")
			self.__sandbox_log = self.read().split()[0]
		self.dont_export_vars = self.read().split()
		# locking isn't used much, but w/ threading this will matter


	def prep_phase(self, phase, env, sandbox=None, logging=None):
		"""
		Utility function, combines multiple calls into one, leaving the processor in a state where all that
		remains is a call start_processing call, then generic_handler event loop.

		@param phase: phase to prep for
		@type phase: str
		@param env: mapping of the environment to prep the processor with
		@param sandbox: should the sandbox be enabled?
		@param logging: None, or a filepath to log the output from the processor to
		@return: True for success, False for everything else
		"""

		self.write("process_ebuild %s" % phase)
		if not self.send_env(env):
			return False
		if sandbox:
			self.set_sandbox_state(sandbox)
		if logging:
			if not self.set_logfile(logging):
				return False
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

	def write(self, string, flush=True):
		"""
		send something to the bash side.
		
		@param string: string to write to the bash processor all strings written are automatically \\n terminated
		@param flush: boolean controlling whether the data is flushed immediately.  Disabling flush is 
		useful when dumping large amounts of data
		"""
		if string[-1] == "\n":
			self.ebd_write.write(string)
		else:
			self.ebd_write.write(string +"\n")
		if flush:
			self.ebd_write.flush()

	def expect(self, want):
		"""
		read from the daemon, and return true or false if the returned string is what is expected
		
		@param want: string we're expecting
		@return: boolean, was what was read == want?
		"""
		got = self.ebd_read.readline()
		return want == got.rstrip("\n")

	def read(self, lines=1):
		"""
		read data from the daemon.  Shouldn't be called except internally
		"""
		mydata = ''
		while lines > 0:
			mydata += self.ebd_read.readline()
			lines -= 1
		return mydata

	def sandbox_summary(self, move_log=False):
		"""
		if the instance is sandboxed, print the sandbox access summary
		
		@param move_log: location to move the sandbox log to if a failure occured
		"""
		if not os.path.exists(self.__sandbox_log):
			self.write("end_sandbox_summary")
			return 0
		violations = portage_util.grabfile(self.__sandbox_log)
		if not violations:
			self.write("end_sandbox_summary")
			return 0
		if not move_log:
			move_log = self.__sandbox_log
		elif move_log != self.__sandbox_log:
			myf = open(move_log)
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
		"""
		this preloades eclasses into a a bash function, thus avoiding the cost of going to disk.
		preloading eutils (which is heaviliy inherited) speeds up regen times for example
		
		@param ec_file: filepath of eclass to preload
		@return: boolean, True for success
		"""
		if not os.path.exists(ec_file):
			return 1
		self.write("preload_eclass %s" % ec_file)
		if self.expect("preload_eclass succeeded"):
			self.preloaded_eclasses = True
			return True
		return False

	def lock(self):
		"""
		lock the processor.  Currently doesn't block any access, but will
		"""
		self.processing_lock = True

	def unlock(self):
		"""
		unlock the processor
		"""
		self.processing_lock = False

	@property
	def locked(self):
		"""
		is the processor locked?
		"""
		return self.processing_lock

	@property
	def is_alive(self):
		"""
		returns if it's known if the processor has been shutdown.
		
		Currently doesn't check to ensure the pid is still running, yet it should
		"""
		try:
			return self.pid is not None
		except AttributeError:
			# thrown only if failure occured instantiation.
			return False

	def shutdown_processor(self):
		"""
		tell the daemon to shut itself down, and mark this instance as dead
		"""
		try:
			if self.is_alive:
				self.write("shutdown_daemon")
				self.ebd_write.close()
				self.ebd_read.close()

				# now we wait.
				os.waitpid(self.pid, 0)

		except (IOError, OSError):
			pass

		# currently, this assumes all went well.
		# which isn't always true.
		self.pid = None

	def set_sandbox_state(self, state):
		"""
		tell the daemon whether to enable the sandbox, or disable it
		@param state: boolean, if True enable sandbox
		"""
		if state:
			self.write("set_sandbox_state 1")
		else:
			self.write("set_sandbox_state 0")

	def send_env(self, env_dict):
		"""
		transfer the ebuild's desired env (env_dict) to the running daemon
		
		@param env_dict: mapping of key -> value pairs to use for the bash env.  all keys/values must be strings
		"""

		self.write("start_receiving_env\n")
		exported_keys = ''
		for x in env_dict:
			if x not in self.dont_export_vars:
				if not x[0].isalpha():
					raise KeyError(x)
				s = env_dict[x].replace("\\", "\\\\\\\\")
				s = s.replace("'", "\\\\'")
				s = s.replace("\n", "\\\n")
				if "'" in s:
					self.write("%s=$'%s'\n" % (x, s), flush=False)
				else:
					self.write("%s=$'%s'\n" % (x, s), flush=False)
				exported_keys += x+' '
		self.write("export " + exported_keys, flush=False)
		self.write("end_receiving_env")
		return self.expect("env_received")

	def set_logfile(self, logfile=''):
		"""
		relevant only when the daemon is sandbox'd, set the logfile.  Set the location to log to
		
		@param logfile: filepath to log to
		"""
		self.write("logging %s" % logfile)
		return self.expect("logging_ack")

	def __del__(self):
		"""simply attempts to notify the daemon to die"""
		# for this to be reached means we ain't in a list no more.
		if self.is_alive:
			# I'd love to know why the exception wrapping is required...
			try:
				self.shutdown_processor()
			except TypeError:
				pass

	def get_keys(self, package_inst, eclass_cache):
		"""
		request the metadata be regenerated from an ebuild
		
		@param package_inst: L{pkgcore.ebuild.ebuild_src.package} instance to regenerate
		@param eclass_cache: L{pkgcore.ebuild.eclass_cache} instance to use for eclass access
		@return: dict when successful, None when failed
		"""

		self.write("process_ebuild depend")
		e = expected_ebuild_env(package_inst)
		e["PATH"] = depends_phase_path
		self.send_env(expected_ebuild_env(package_inst))
		self.set_sandbox_state(True)
		self.write("start_processing")

		metadata_keys = {}
		val = self.generic_handler(additional_commands={ \
			"request_inherit":post_curry(self.__class__._inherit, eclass_cache), \
			"key":post_curry(self.__class__._receive_key, metadata_keys) } )

		if not val:
			logging.error("returned val from get_keys was '%s'" % str(val))
			raise Exception(val)

		return metadata_keys

	def _receive_key(self, line, keys_dict):
		"""
		internal function used for receiving keys from the bash processor
		"""
		line = line.split("=", 1)
		if len(line) != 2:
			raise FinishedProcessing(True)
		else:
			keys_dict[line[0]] = line[1]

	def _inherit(self, line, ecache):
		"""
		callback for implementing inherit digging into eclass_cache.  not for normal consumption.
		"""
		if line is None:
			self.write("failed")
			raise UnhandledCommand("inherit requires an eclass specified, none specified")

		line = line.strip()
		eclass = ecache.get_eclass(line)
		if eclass is None:
			value = ecache.write("failed")
			raise UnhandledCommand("inherit requires a known eclass, %s cannot be found" % line)

		if eclass.get_path is not None:
			value = eclass.get_path()
			self.write("path")
			self.write(value)
		else:
			# $10 this doesn't work.
			value = eclass.get_fileobj().read()
			self.write("transfer")
			self.write(value)

	# this basically handles all hijacks from the daemon, whether confcache or portageq.
	def generic_handler(self, additional_commands=None):
		"""
		internal event handler that responds to the running ebuild processor's requests

		@param additional_commands: is a dict of command:callable.  If you need to slip in extra args, look into pkgcore.util.currying.
		commands names cannot have spaces.  the callable is called with the processor as first arg, and
		remaining string (None if no remaining fragment) as second arg.
		If you need to split the args to command, whitespace splitting falls to your func.

		@raise UnhandledCommand: thrown when an unknown command is encountered.
		"""

		# note that self is passed in.  so... we just pass in the unbound instance.  Specifically, via digging through __class__
		# if you don't do it, sandbox_summary (fex) cannot be overriden, this func will just use this classes version.
		# so dig through self.__class__ for it. :P

		handlers = {"request_sandbox_summary":(self.__class__.sandbox_summary, [], {})}
		f = post_curry(chuck_UnhandledCommand, False)
		for x in ("prob", "env_receiving_failed"):
			handlers[x] = f
		del f

		handlers["phases"] = pre_curry(chuck_StoppingCommand, lambda f: f.lower().strip() == "succeeded")

		if additional_commands is not None:
			for x in additional_commands:
				if not callable(additional_commands[x]):
					raise TypeError(additional_commands[x])

			handlers.update(additional_commands)

		try:
			while True:
				line = self.read().strip()
				# split on first whitespace.
				s = line.split(None, 1)
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

def chuck_StoppingCommand(val, processor, *args):
	if callable(val):
		raise FinishedProcessing(val(args[0]))
	raise FinishedProcessing(val)


class ProcessingInterruption(Exception):
	pass


class FinishedProcessing(ProcessingInterruption):

	def __init__(self, val, msg=None):
		self.val, self.msg = val, msg

	def __str__(self):
		return "Finished processing with val, %s" % str(self.val)


class UnhandledCommand(ProcessingInterruption):

	def __init__(self, line=None):
		self.line=line

	def __str__(self):
		return "unhandled command, %s" % self.line


def expected_ebuild_env(pkg, d=None):
	"""
	setup expected ebuild vars
	
	@param d: if None, generates a dict, else modifies a passed in mapping
	@return: mapping
	"""
	if d is None:
		d = {}
	d["CATEGORY"] = pkg.category
	d["PF"] = "-".join((pkg.package, pkg.fullver))
	d["P"]  = "-".join((pkg.package, pkg.version))
	d["PN"] = pkg.package
	d["PV"] = pkg.version
	if pkg.revision is None:
		d["PR"] = "r0"
	else:
		d["PR"] = "r%i" % pkg.revision
	d["PVR"] = pkg.fullver
	d["EBUILD"] = pkg.path
	d["PATH"] = ":".join(EBUILD_ENV_PATH + d.get("PATH", "").split(":"))
	return d

