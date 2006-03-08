# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: spawn.py 2283 2005-11-10 00:35:14Z ferringb $

__all__ = ["cleanup_pids", "spawn","spawn_sandbox", "spawn_bash", "spawn_fakeroot", "spawn_get_output"]

import os, atexit, signal, sys

from portage.util.mappings import ProtectedDict
from portage.const import BASH_BINARY, SANDBOX_BINARY, FAKEROOT_PATH


try:
	import resource
	max_fd_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
except ImportError:
	max_fd_limit = 256

sandbox_capable = (os.path.isfile(SANDBOX_BINARY) and
                   os.access(SANDBOX_BINARY, os.X_OK))
userpriv_capable = (os.getuid() == 0)
fakeroot_capable = False


def spawn_bash(mycommand, debug=False, opt_name=None, **keywords):
	"""spawn the command via bash -c"""
	
	args = [BASH_BINARY]
	if not opt_name:
		opt_name = os.path.basename(mycommand.split()[0])
	if debug:
		# Print commands and their arguments as they are executed.
		args.append("-x")
	args.append("-c")
	args.append(mycommand)
	return spawn(args, opt_name=opt_name, **keywords)

def spawn_sandbox(mycommand, opt_name=None, **keywords):
	"""spawn the command under sandboxed"""
	
	if not sandbox_capable:
		return spawn_bash(mycommand, opt_name=opt_name, **keywords)
	args=[SANDBOX_BINARY]
	if not opt_name:
		opt_name = os.path.basename(mycommand.split()[0])
	args.append(mycommand)
	return spawn(args, opt_name=opt_name, **keywords)

_exithandlers = []
def atexit_register(func, *args, **kargs):
	"""Wrapper around atexit.register that is needed in order to track
	what is registered.  For example, when portage restarts itself via
	os.execv, the atexit module does not work so we have to do it
	manually by calling the run_exitfuncs() function in this module."""
	_exithandlers.append((func, args, kargs))

def run_exitfuncs():
	"""This should behave identically to the routine performed by
	the atexit module at exit time.  It's only necessary to call this
	function when atexit will not work (because of os.execv, for
	example)."""

	# This function is a copy of the private atexit._run_exitfuncs()
	# from the python 2.4.2 sources.  The only difference from the
	# original function is in the output to stderr.
	exc_info = None
	while _exithandlers:
		func, targs, kargs = _exithandlers.pop()
		try:
			func(*targs, **kargs)
		except SystemExit:
			exc_info = sys.exc_info()
		except:
			exc_info = sys.exc_info()

	if exc_info is not None:
		raise exc_info[0], exc_info[1], exc_info[2]

atexit.register(run_exitfuncs)

# We need to make sure that any processes spawned are killed off when
# we exit. spawn() takes care of adding and removing pids to this list
# as it creates and cleans up processes.
spawned_pids = []
def cleanup_pids(pids=None):
	"""reap pids if specified, else all children"""
	global spawned_pids
	if pids == None:
		pids = spawned_pids
	while pids:
		pid = pids.pop()
		try:
			if os.waitpid(pid, os.WNOHANG) == (0, 0):
				os.kill(pid, signal.SIGTERM)
				os.waitpid(pid, 0)
		except OSError:
			# This pid has been cleaned up outside
			# of spawn().
			pass

		if spawned_pids is not pids:
			try:
				spawned_pids.remove(pid)
			except ValueError:
				pass
		
def spawn(mycommand, env={}, opt_name=None, fd_pipes=None, returnpid=False,
          uid=None, gid=None, groups=None, umask=None, logfile=None,
          path_lookup=True):

	"""wrapper around execve
	
	mycommand must be either a list, or a string
	env must be a dict with it's keys strictly strings, and values strictly strings
	opt_name controls what the process is named (what it would show up as under top for example)
	fd_pipes controls what fd's are left open in the spawned process- must be a dict mapping existing
	fd to fd # inside the new process
	returnpid controls whether spawn waits for the process to finish, or returns the pid.
	
	rest of the options are fairly self explanatory"""
	global spawned_pids
	# mycommand is either a str or a list
	if isinstance(mycommand, str):
		mycommand = mycommand.split()

	# If an absolute path to an executable file isn't given
	# search for it unless we've been told not to.
	binary = mycommand[0]
	if (not os.path.isabs(binary) or not os.path.isfile(binary)
	    or not os.access(binary, os.X_OK)):
		binary = path_lookup and find_binary(binary) or None
		if not binary:
			return -1

	# If we haven't been told what file descriptors to use
	# default to propogating our stdin, stdout and stderr.
	if fd_pipes is None:
		fd_pipes = {0:0, 1:1, 2:2}

	# mypids will hold the pids of all processes created.
	mypids = []

	if logfile:
		# Using a log file requires that stdout and stderr
		# are assigned to the process we're running.
		if 1 not in fd_pipes or 2 not in fd_pipes:
			raise ValueError(fd_pipes)

		# Create a pipe
		(pr, pw) = os.pipe()

		# Create a tee process, giving it our stdout and stderr
		# as well as the read end of the pipe.
		mypids.extend(spawn(('tee', '-i', '-a', logfile),
		              returnpid=True, fd_pipes={0:pr,
		              1:fd_pipes[1], 2:fd_pipes[2]}))

		# We don't need the read end of the pipe, so close it.
		os.close(pr)

		# Assign the write end of the pipe to our stdout and stderr.
		fd_pipes[1] = pw
		fd_pipes[2] = pw

	pid = os.fork()

	if not pid:
		try:
			_exec(binary, mycommand, opt_name, fd_pipes,
			      env, gid, groups, uid, umask)
		except Exception, e:
			# We need to catch _any_ exception so that it doesn't
			# propogate out of this function and cause exiting
			# with anything other than os._exit()
			sys.stderr.write("%s:\n   %s\n" % (e, " ".join(mycommand)))
			os._exit(1)

	# Add the pid to our local and the global pid lists.
	mypids.append(pid)
	spawned_pids.append(pid)

	# If we started a tee process the write side of the pipe is no
	# longer needed, so close it.
	if logfile:
		os.close(pw)

	# If the caller wants to handle cleaning up the processes, we tell
	# it about all processes that were created.
	if returnpid:
		return mypids

	try:
		# Otherwise we clean them up.
		while mypids:

			# Pull the last reader in the pipe chain. If all processes
			# in the pipe are well behaved, it will die when the process
			# it is reading from dies.
			pid = mypids.pop(0)

			# and wait for it.
			retval = os.waitpid(pid, 0)[1]

			# When it's done, we can remove it from the
			# global pid list as well.
			spawned_pids.remove(pid)

			if retval:
				# If it failed, kill off anything else that
				# isn't dead yet.
				for pid in mypids:
					if os.waitpid(pid, os.WNOHANG) == (0,0):
						os.kill(pid, signal.SIGTERM)
						os.waitpid(pid, 0)
					spawned_pids.remove(pid)

				return process_exit_code(retval)
	finally:
		cleanup_pids(mypids)

	# Everything succeeded
	return 0

def _exec(binary, mycommand, opt_name, fd_pipes, env, gid, groups, uid, umask):
	"""internal function to handle exec'ing the child process"""
	
	# If the process we're creating hasn't been given a name
	# assign it the name of the executable.
	if not opt_name:
		opt_name = os.path.basename(binary)

	# Set up the command's argument list.
	myargs = [opt_name]
	myargs.extend(mycommand[1:])

	# Set up the command's pipes.
	my_fds = {}
	# To protect from cases where direct assignment could
	# clobber needed fds ({1:2, 2:1}) we first dupe the fds
	# into unused fds.
	for fd in fd_pipes:
		my_fds[fd] = os.dup(fd_pipes[fd])
	# Then assign them to what they should be.
	for fd in my_fds:
		os.dup2(my_fds[fd], fd)
	# Then close _all_ fds that haven't been explictly
	# requested to be kept open.
	for fd in range(max_fd_limit):
		if fd not in my_fds:
			try:
				os.close(fd)
			except OSError:
				pass

	# Set requested process permissions.
	if gid:
		os.setgid(gid)
	if groups:
		os.setgroups(groups)
	if uid:
		os.setuid(uid)
	if umask:
		os.umask(umask)

	# And switch to the new process.
	os.execve(binary, myargs, env)

def find_binary(binary):
	"""look through the PATH environment, finding the binary to execute"""
	
	for path in os.getenv("PATH", "").split(":"):
		filename = "%s/%s" % (path, binary)
		if os.access(filename, os.X_OK) and os.path.isfile(filename):
			return filename

	raise CommandNotFound(binary)

def spawn_fakeroot(mycommand, save_file, env=None, opt_name=None, **keywords):
	"""spawn a process via fakeroot
	
	refer to the fakeroot manpage for specifics of using fakeroot
	"""
	
	if env is None:
		env = {}
	else:
		env = ProtectedDict(env)
	if opt_name is None:
		opt_name = "fakeroot %s" % mycommand
	args = [FAKEROOT_PATH, "-u", "-b", "20", "-s", save_file]
	if os.path.exists(savefile):
		args.extend(["-i", save_file])
	args.append("--")
	return spawn(args, opt_name=opt_name, env=env, **keywords)

def spawn_get_output(mycommand, spawn_type=spawn, raw_exit_code=False, collect_fds=[1],
	fd_pipes=None, **keywords):

	"""call spawn, collecting the output to fd's specified in collect_fds list
	emulate_gso is a compatability hack to emulate commands.getstatusoutput's return, minus the
	requirement it always be a bash call (spawn_type controls the actual spawn call), and minus the
	'lets let log only stdin and let stderr slide by'.
	spawn_type is the passed in function to call- typically spawn_bash, spawn, spawn_sandbox, or spawn_fakeroot
	"""

	pr, pw = None, None
	if fd_pipes is None:
		fd_pipes = {0:0}
	else:
		fd_pipes = ProtectedDict(fd_pipes)
	try:
		pr, pw = os.pipe()
		for x in collect_fds:
			fd_pipes[x] = pw
		keywords["returnpid"] = True
		mypid=spawn_type(mycommand,fd_pipes=fd_pipes,**keywords)
		os.close(pw)
		pw = None

		if not isinstance(mypid, (list, tuple)):
			raise ExecutionFailure()

		fd = os.fdopen(pr, "r")
		try:
			mydata = fd.readlines()
		finally:
			fd.close()
			pw = None
	
		retval = os.waitpid(mypid[0],0)[1]
		cleanup_pids(mypid)
		if raw_exit_code:
			return [retval,mydata]
		retval = process_exit_code(retval)
		return [retval, mydata]

	finally:
		if pr is not None:
			try: os.close(pr)
			except OSError: pass
		if pw is not None:
			try: os.close(pw)
			except OSError: pass

def process_exit_code(retval):
	"""process a waitpid returned exit code, returning exit code if it exit'd, or the
	signal if it died from signalling
	if throw_signals is on, it raises a SystemExit if the process was signaled.
	This is intended for usage with threads, although at the moment you can't signal individual
	threads in python, only the master thread, so it's a questionable option."""


	# If it got a signal, return the signal that was sent.
	if retval & 0xff:
		return (retval & 0xff) << 8

	# Otherwise, return its exit code.
	return retval >> 8


class ExecutionFailure(Exception):
	pass

class CommandNotFound(ExecutionFailure):
	def __init__(self, command):
		self.command=command
	def __str__(self):
		return "CommandNotFound Exception: Couldn't find '%s'" % str(self.command)

if os.path.exists(FAKEROOT_PATH):
	try:
		r,s = spawn_get_output((FAKEROOT_PATH, "--version"), fd_pipes={1:1,2:2})
		fakeroot_capable = (r == 0) and (len(s) == 1) and ("version 1." in s[0])
	except ExecutionFailure:
		fakeroot_capable = False
				
	
