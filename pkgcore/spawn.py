# Copyright: 2005-2006 Jason Stubbs <jstubbs@gmail.com>
# Copyright: 2004-2006 Brian Harring <ferringb@gmail.com>
# Copyright: 2004-2005 Gentoo Foundation
# License: GPL2


"""
subprocess related functionality
"""

__all__ = [
    "cleanup_pids", "spawn", "spawn_sandbox", "spawn_bash", "spawn_fakeroot",
    "spawn_get_output", "find_binary"]

import os, atexit, signal, sys

from pkgcore.util.mappings import ProtectedDict
from pkgcore.const import (
    BASH_BINARY, SANDBOX_BINARY, FAKED_PATH, LIBFAKEROOT_PATH)

try:
    import resource
    max_fd_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
except ImportError:
    max_fd_limit = 256

def slow_get_open_fds():
    return xrange(max_fd_limit)
if os.path.isdir("/proc/%i/fd" % os.getpid()):
    def get_open_fds():
        try:
            return map(int, os.listdir("/proc/%i/fd" % os.getpid()))
        except ValueError, v:
            import warnings
            warnings.warn(
                "extremely odd, got a value error '%s' while scanning "
                "/proc/%i/fd; OS allowing string names in fd?" %
                (v, os.getpid()))
            return slow_get_open_fds()
else:
    get_open_fds = slow_get_open_fds

# this should be JIT determination.
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
    args = [SANDBOX_BINARY]
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
    """reap list of pids if specified, else all children"""

    if pids is None:
        pids = spawned_pids
    elif pids is not spawned_pids:
        pids = list(pids)

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

def spawn(mycommand, env=None, opt_name=None, fd_pipes=None, returnpid=False,
          uid=None, gid=None, groups=None, umask=None, logfile=None,
          path_lookup=True):

    """wrapper around execve

    @type  mycommand: list or string
    @type  env: mapping with string keys and values
    @param opt_name: controls what the process is named
        (what it would show up as under top for example)
    @type  fd_pipes: mapping from existing fd to fd (inside the new process)
    @param fd_pipes: controls what fd's are left open in the spawned process-
    @param returnpid: controls whether spawn waits for the process to finish,
        or returns the pid.

    rest of the options are fairly self explanatory.
    """
    if env is None:
        env = {}
    global spawned_pids
    # mycommand is either a str or a list
    if isinstance(mycommand, str):
        mycommand = mycommand.split()

    # If an absolute path to an executable file isn't given
    # search for it unless we've been told not to.
    binary = mycommand[0]
    if not path_lookup:
        if find_binary(binary) != binary:
            raise CommandNotFound(binary)
    else:
        binary = find_binary(binary)

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
        mypids.extend(spawn(('tee', '-i', '-a', logfile), returnpid=True,
            fd_pipes={0:pr, 1:fd_pipes[1], 2:fd_pipes[2]}))

        # We don't need the read end of the pipe, so close it.
        os.close(pr)

        # Assign the write end of the pipe to our stdout and stderr.
        fd_pipes[1] = pw
        fd_pipes[2] = pw


    pid = os.fork()

    if not pid:
        # 'Catch "Exception"'
        # pylint: disable-msg=W0703
        try:
            _exec(binary, mycommand, opt_name, fd_pipes, env, gid, groups,
                  uid, umask)
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
                    if os.waitpid(pid, os.WNOHANG) == (0, 0):
                        os.kill(pid, signal.SIGTERM)
                        os.waitpid(pid, 0)
                    spawned_pids.remove(pid)

                return process_exit_code(retval)
    finally:
        cleanup_pids(mypids)

    # Everything succeeded
    return 0

def _exec(binary, mycommand, opt_name, fd_pipes, env, gid, groups, uid, umask):
    """internal function to handle exec'ing the child process.

    If it succeeds this function does not return. It might raise an
    exception, and since this runs after fork calling code needs to
    make sure this is caught and os._exit is called if it does (or
    atexit handlers run twice).
    """

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
    for fd in get_open_fds():
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

    if os.path.isabs(binary):
        if not (os.path.isfile(binary) and os.access(binary, os.X_OK)):
            raise CommandNotFound(binary)
        return binary

    for path in os.environ.get("PATH", "").split(":"):
        filename = "%s/%s" % (path, binary)
        if os.access(filename, os.X_OK) and os.path.isfile(filename):
            return filename

    raise CommandNotFound(binary)

def spawn_fakeroot(mycommand, save_file, env=None, opt_name=None,
                   returnpid=False, **keywords):
    """spawn a process via fakeroot

    refer to the fakeroot manpage for specifics of using fakeroot
    """
    if env is None:
        env = {}
    else:
        env = ProtectedDict(env)

    if opt_name is None:
        opt_name = "fakeroot %s" % mycommand

    args = [
        FAKED_PATH,
        "--unknown-is-real", "--foreground", "--save-file", save_file]

    rd_fd, wr_fd = os.pipe()
    daemon_fd_pipes = {1:wr_fd, 2:wr_fd}
    if os.path.exists(save_file):
        args.append("--load")
        daemon_fd_pipes[0] = os.open(save_file, os.O_RDONLY)
    else:
        daemon_fd_pipes[0] = os.open("/dev/null", os.O_RDONLY)

    pids = None
    pids = spawn(args, fd_pipes=daemon_fd_pipes, returnpid=True)
    try:
        try:
            rd_f = os.fdopen(rd_fd)
            line = rd_f.readline()
            rd_f.close()
            rd_fd = None
        except:
            cleanup_pids(pids)
            raise
    finally:
        for x in (rd_fd, wr_fd, daemon_fd_pipes[0]):
            if x is not None:
                try:
                    os.close(x)
                except OSError:
                    pass

    line = line.strip()

    try:
        fakekey, fakepid = map(int, line.split(":"))
    except ValueError:
        raise ExecutionFailure("output from faked was unparsable- %s" % line)

    # by now we have our very own daemonized faked.  yay.
    env["FAKEROOTKEY"] = str(fakekey)
    env["LD_PRELOAD"] = ":".join(
        [LIBFAKEROOT_PATH] + env.get("LD_PRELOAD", "").split(":"))

    try:
        ret = spawn(
            mycommand, opt_name=opt_name, env=env, returnpid=returnpid,
            **keywords)
        if returnpid:
            return ret + [fakepid] + pids
        return ret
    finally:
        if not returnpid:
            cleanup_pids([fakepid] + pids)

def spawn_get_output(
    mycommand, spawn_type=spawn, raw_exit_code=False, collect_fds=(1,),
    fd_pipes=None, split_lines=True, **keywords):

    """Call spawn, collecting the output to fd's specified in collect_fds list.

    @param spawn_type: the passed in function to call-
       typically spawn_bash, spawn, spawn_sandbox, or spawn_fakeroot.
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
        mypid = spawn_type(mycommand, fd_pipes=fd_pipes, **keywords)
        os.close(pw)
        pw = None

        if not isinstance(mypid, (list, tuple)):
            raise ExecutionFailure()

        fd = os.fdopen(pr, "r")
        try:
            if not split_lines:
                mydata = fd.read()
            else:
                mydata = fd.readlines()
        finally:
            fd.close()
            pw = None

        retval = os.waitpid(mypid[0], 0)[1]
        cleanup_pids(mypid)
        if raw_exit_code:
            return [retval, mydata]
        return [process_exit_code(retval), mydata]

    finally:
        if pr is not None:
            try:
                os.close(pr)
            except OSError:
                pass
        if pw is not None:
            try:
                os.close(pw)
            except OSError:
                pass

def process_exit_code(retval):
    """Process a waitpid returned exit code.

    @return: The exit code if it exit'd, the signal if it died from signalling.
    """
    # If it got a signal, return the signal that was sent.
    if retval & 0xff:
        return (retval & 0xff) << 8

    # Otherwise, return its exit code.
    return retval >> 8


class ExecutionFailure(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)
        self.msg = msg
    def __str__(self):
        return "Execution Failure: %s" % self.msg

class CommandNotFound(ExecutionFailure):
    def __init__(self, command):
        ExecutionFailure.__init__(
            self, "CommandNotFound Exception: Couldn't find '%s'" % (command,))
        self.command = command


if os.path.exists(FAKED_PATH) and os.path.exists(LIBFAKEROOT_PATH):
    try:
        r, s = spawn_get_output(["fakeroot", "--version"], fd_pipes={2:1, 1:1})
        fakeroot_capable = (r == 0) and (len(s) == 1) and ("version 1." in s[0])
    except ExecutionFailure:
        fakeroot_capable = False


