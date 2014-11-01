# Copyright: 2004-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD


"""
low level ebuild processor.

This basically is a coprocessor that controls a bash daemon for actual
ebuild execution. Via this, the bash side can reach into the python
side (and vice versa), enabling remote trees (piping data from python
side into bash side for example).

A couple of processors are left lingering while pkgcore is running for
the purpose of avoiding spawning overhead, this (and the general
design) reduces regen time by over 40% compared to portage-2.1
"""

# this needs work. it's been pruned heavily from what ebd used
# originally, but it still isn't what I would define as 'right'


__all__ = (
    "request_ebuild_processor", "release_ebuild_processor", "EbuildProcessor",
    "UnhandledCommand", "expected_ebuild_env")

try:
    import threading
    _global_ebp_lock = threading.Lock()
    _acquire_global_ebp_lock = _global_ebp_lock.acquire
    _release_global_ebp_lock = _global_ebp_lock.release
except ImportError:
    def _acquire_global_ebp_lock():
        pass

    def _release_global_ebp_lock():
        pass


inactive_ebp_list = []
active_ebp_list = []

from __future__ import print_function

import contextlib
import errno
import os
import signal

import pkgcore.spawn
from pkgcore import const, os_data
from pkgcore.ebuild import const as e_const

from snakeoil import klass
from snakeoil.currying import post_curry, partial, pretty_docs
from snakeoil.osutils import abspath, normpath, pjoin
from snakeoil.weakrefs import WeakRefFinalizer
from snakeoil.demandload import demandload
demandload(globals(),
    'pkgcore.log:logger',
    'snakeoil:fileutils',
    'traceback',
)


def _single_thread_allowed(functor):
    def _inner(*args, **kwds):
        _acquire_global_ebp_lock()
        try:
            return functor(*args, **kwds)
        finally:
            _release_global_ebp_lock()
    _inner.func = functor
    pretty_docs(_inner, name=functor.__name__)
    return _inner

@_single_thread_allowed
def forget_all_processors():
    active_ebp_list[:] = []
    inactive_ebp_list[:] = []


@_single_thread_allowed
def shutdown_all_processors():
    """kill off all known processors"""
    try:
        while active_ebp_list:
            try:
                active_ebp_list.pop().shutdown_processor(
                    ignore_keyboard_interrupt=True)
            except EnvironmentError:
                pass

        while inactive_ebp_list:
            try:
                inactive_ebp_list.pop().shutdown_processor(
                    ignore_keyboard_interrupt=True)
            except EnvironmentError:
                pass
    except Exception as e:
        traceback.print_exc()
        print(e)
        raise

pkgcore.spawn.atexit_register(shutdown_all_processors)

@_single_thread_allowed
def request_ebuild_processor(userpriv=False, sandbox=None, fakeroot=False,
                             save_file=None):
    """
    request an ebuild_processor instance, creating a new one if needed.

    Note that fakeroot processes are B{never} reused due to the fact
    the fakeroot env becomes localized to the pkg it's handling.

    :return: :obj:`EbuildProcessor`
    :param userpriv: should the processor be deprived to
        :obj:`pkgcore.os_data.portage_gid` and :obj:`pkgcore.os_data.portage_uid`?
    :param sandbox: should the processor be sandboxed?
    :param fakeroot: should the processor be fakerooted?  This option is
        mutually exclusive to sandbox, and requires save_file to be set.
    :param save_file: location to store fakeroot state dumps
    """

    if sandbox is None:
        sandbox = pkgcore.spawn.is_sandbox_capable()

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

@_single_thread_allowed
def release_ebuild_processor(ebp):
    """
    the inverse of request_ebuild_processor.

    Any processor requested via request_ebuild_processor B{must} be released
    via this function once it's no longer in use.
    This includes fakerooted processors.

    :param ebp: :obj:`EbuildProcessor` instance
    :return: boolean indicating release results- if the processor isn't known
        as active, False is returned.
        If a processor isn't known as active, this means either calling
        error or an internal error.
    """

    try:
        active_ebp_list.remove(ebp)
    except ValueError:
        return False

    assert ebp not in inactive_ebp_list
    # if it's a fakeroot'd process, we throw it away.
    # it's not useful outside of a chain of calls
    if ebp.onetime() or ebp.locked:
        # ok, so the thing is not reusable either way.
        ebp.shutdown_processor()
    else:
        inactive_ebp_list.append(ebp)
    return True


@contextlib.contextmanager
def reuse_or_request(ebp=None, **request_kwds):
    """Do a processor operation, locking as necessary.

    If the processor is given, it's assumed to be locked already.
    If no processor is given, one is allocated, then released upon
    finishing."""
    release_required = ebp is None
    try:
        if ebp is None:
            ebp = request_ebuild_processor(**request_kwds)
        yield ebp
    finally:
        if release_required and ebp is not None:
            release_ebuild_processor(ebp)


class ProcessingInterruption(Exception):
    pass

class FinishedProcessing(ProcessingInterruption):

    def __init__(self, val, msg=None):
        ProcessingInterruption.__init__(
            self, "Finished processing with val, %s" % (val,))
        self.val, self.msg = val, msg

class UnhandledCommand(ProcessingInterruption):

    def __init__(self, line=None):
        ProcessingInterruption.__init__(
            self, "unhandled command, %s" % (line,))
        self.line = line
        self.args = (line,)

class InternalError(ProcessingInterruption):

    def __init__(self, line=None, msg=None):
        ProcessingInterruption.__init__(
            self, "Internal error occurred: line=%r, msg=%r"
            % (line, msg))
        self.line, self.msg = line, msg
        self.args = (line, msg)

def chuck_KeyboardInterrupt(*arg):
    raise KeyboardInterrupt("ctrl+c encountered")

def chuck_UnhandledCommand(processor, line):
    raise UnhandledCommand(line)

def chuck_StoppingCommand(val, processor, *args):
    if callable(val):
        raise FinishedProcessing(val(args[0]))
    raise FinishedProcessing(val)


class InitializationError(Exception):
    pass


class EbuildProcessor(object):

    """abstraction of a running ebuild.sh instance.

    Contains the env, functions, etc that ebuilds expect.
    """

    __metaclass__ = WeakRefFinalizer

    def __init__(self, userpriv, sandbox, fakeroot, save_file):
        """
        :param sandbox: enables a sandboxed processor
        :param userpriv: enables a userpriv'd processor
        :param fakeroot: enables a fakeroot'd processor-
            this is a mutually exclusive option to sandbox, and
            requires userpriv to be enabled. Violating this will
            result in nastiness.
        """

        self.lock()
        self.ebd = e_const.EBUILD_DAEMON_PATH
        spawn_opts = {'umask':0002}

        self._preloaded_eclasses = {}
        self._eclass_caching = False
        self._outstanding_expects = []
        self._metadata_paths = None

        if fakeroot and (sandbox or not userpriv):
            traceback.print_stack()
            logger.error("Both sandbox and fakeroot cannot be enabled at the same time")
            raise InitializationError("cannot initialize with sandbox and fakeroot")

        if userpriv:
            self.__userpriv = True
            spawn_opts.update({
                    "uid":os_data.portage_uid, "gid":os_data.portage_gid,
                    "groups":[os_data.portage_gid]})
        else:
            if pkgcore.spawn.is_userpriv_capable():
                spawn_opts.update({"gid":os_data.portage_gid,
                                   "groups":[0, os_data.portage_gid]})
            self.__userpriv = False

        # open the pipes to be used for chatting with the new daemon
        cread, cwrite = os.pipe()
        dread, dwrite = os.pipe()
        self.__sandbox = False
        self.__fakeroot = False

        # since it's questionable which spawn method we'll use (if
        # sandbox or fakeroot fex), we ensure the bashrc is invalid.
        env = {x: "/etc/portage/spork/not/valid/ha/ha"
               for x in ("BASHRC", "BASH_ENV")}
        if int(os.environ.get('PKGCORE_PERF_DEBUG', 1)) > 1:
            env["PKGCORE_PERF_DEBUG"] = os.environ['PKGCORE_PERF_DEBUG']

        # append script dir to PATH for git repo or unpacked tarball
        if "PKGCORE_SCRIPT_PATH" in os.environ:
            env["PATH"] = os.environ["PATH"] + os.pathsep + os.environ["PKGCORE_SCRIPT_PATH"]

        args = []
        if sandbox:
            if not pkgcore.spawn.is_sandbox_capable():
                raise ValueError("spawn lacks sandbox capabilities")
            if fakeroot:
                raise InitializationError('fakeroot was on, but sandbox was also on')
            self.__sandbox = True
            spawn_func = pkgcore.spawn.spawn_sandbox
#            env.update({"SANDBOX_DEBUG":"1", "SANDBOX_DEBUG_LOG":"/var/tmp/test"})

        elif fakeroot:
            if not pkgcore.spawn.is_fakeroot_capable():
                raise ValueError("spawn lacks fakeroot capabilities")
            self.__fakeroot = True
            spawn_func = pkgcore.spawn.spawn_fakeroot
            args.append(save_file)
        else:
            spawn_func = pkgcore.spawn.spawn

        # force to a neutral dir so that sandbox/fakeroot won't explode if
        # ran from a nonexistent dir
        spawn_opts["cwd"] = e_const.EAPI_BIN_PATH
        # little trick. we force the pipes to be high up fd wise so
        # nobody stupidly hits 'em.
        max_fd = min(pkgcore.spawn.max_fd_limit, 1024)
        env.update({
            "PKGCORE_EBD_READ_FD": str(max_fd-2), "PKGCORE_EBD_WRITE_FD": str(max_fd-1)})
        self.pid = spawn_func(["/bin/bash", self.ebd, "daemonize"], \
            fd_pipes={0:0, 1:1, 2:2, max_fd-2:cread, max_fd-1:dwrite}, \
            returnpid=True, env=env, *args, **spawn_opts)[0]

        os.close(cread)
        os.close(dwrite)
        self.ebd_write = os.fdopen(cwrite, "w")
        self.ebd_read  = os.fdopen(dread, "r")

        # basically a quick "yo" to the daemon
        self.write("dude?")
        if not self.expect("dude!"):
            print("error in server coms, bailing.")
            raise InitializationError(
                "expected 'dude!' response from ebd, which wasn't received. "
                "likely a bug")
        self.write(e_const.EAPI_BIN_PATH)
        # send PKGCORE_PYTHON_BINARY...
        self.write(pkgcore.spawn.find_invoking_python())
        self.write(normpath(abspath(pjoin(
            pkgcore.__file__, os.pardir, os.pardir))))
        if self.__sandbox:
            self.write("sandbox_log?")
            self.__sandbox_log = self.read().split()[0]
        self.dont_export_vars = self.read().split()
        # locking isn't used much, but w/ threading this will matter
        self.unlock()

    def run_phase(self, phase, env, tmpdir, logging=None,
                  additional_commands=None, sandbox=True):
        """
        Utility function, to initialize the processor for a phase.

        Used to combine multiple calls into one, leaving the processor
        in a state where all that remains is a call start_processing
        call, then generic_handler event loop.

        :param phase: phase to prep for
        :type phase: str
        :param env: mapping of the environment to prep the processor with
        :param sandbox: should the sandbox be enabled?
        :param logging: None, or a filepath to log the output from the
            processor to
        :return: True for success, False for everything else
        """

        self.write("process_ebuild %s" % phase)
        if not self.send_env(env, tmpdir=tmpdir):
            return False
        if sandbox:
            self.set_sandbox_state(sandbox)
        if logging:
            if not self.set_logfile(logging):
                return False
        self.write("start_processing")
        return self.generic_handler(additional_commands=additional_commands)

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
        """Is this instance going to be discarded after usage (fakerooted)?"""
        return self.__fakeroot

    def write(self, string, flush=True, disable_runtime_exceptions=False,
              append_newline=True):
        """send something to the bash side.

        :param string: string to write to the bash processor.
            All strings written are automatically \\n terminated.
        :param flush: boolean controlling whether the data is flushed
            immediately.  Disabling flush is useful when dumping large
            amounts of data.
        """
        string = str(string)
        try:
            if append_newline:
                if string != '\n':
                    string += "\n"
            #logger.debug("wrote %i: %s" % (len(string), string))
            self.ebd_write.write(string)
            if flush:
                self.ebd_write.flush()
        except IOError as ie:
            if ie.errno == errno.EPIPE and not disable_runtime_exceptions:
                raise RuntimeError(ie)
            raise

    def _consume_async_expects(self):
        if any(x[0] for x in self._outstanding_expects):
            self.ebd_write.flush()
        got = [x.rstrip('\n') for x in self.readlines(len(self._outstanding_expects))]
        ret = (got == [x[1] for x in self._outstanding_expects])
        self._outstanding_expects = []
        return ret

    def expect(self, want, async=False, flush=False):
        """read from the daemon, check if the returned string is expected.

        :param want: string we're expecting
        :return: boolean, was what was read == want?
        """
        if async:
            self._outstanding_expects.append((flush, want))
            return True
        if flush:
            self.ebd_write.flush()
        if not self._outstanding_expects:
            return want == self.read().rstrip('\n')
        self._outstanding_expects.append((flush, want))
        return self._consume_async_expects()

    def readlines(self, lines, ignore_killed=False):
        mydata = []
        while lines > 0:
            mydata.append(self.ebd_read.readline())
            if mydata[-1].startswith("killed"):
#                self.shutdown_processor()
                chuck_KeyboardInterrupt()
            lines -= 1
        return mydata

    def read(self, lines=1, ignore_killed=False):
        """
        read data from the daemon.  Shouldn't be called except internally
        """
        return "\n".join(self.readlines(lines, ignore_killed=ignore_killed))

    def sandbox_summary(self, move_log=False):
        """
        if the instance is sandboxed, print the sandbox access summary

        :param move_log: location to move the sandbox log to if a failure
            occurred
        """
        if not os.path.exists(self.__sandbox_log):
            self.write("end_sandbox_summary")
            return 0
        with open(self.__sandbox_log, "r") as f:
            violations = [x.strip() for x in f if x.strip()]
        if not violations:
            self.write("end_sandbox_summary")
            return 0
        if not move_log:
            move_log = self.__sandbox_log
        elif move_log != self.__sandbox_log:
            with open(move_log) as myf:
                for x in violations:
                    myf.write(x+"\n")
        # XXX this is fugly, use a colorizer or something
        # (but it is better than "from output import red" (portage's output))
        def red(text):
            return '\x1b[31;1m%s\x1b[39;49;00m' % (text,)
        self.ebd_write.write(red(
                "--------------------------- ACCESS VIOLATION SUMMARY "
                "---------------------------")+"\n")
        self.ebd_write.write(red("LOG FILE = \"%s\"" % move_log)+"\n\n")
        for x in violations:
            self.ebd_write.write(x+"\n")
        self.write(red(
                "-----------------------------------------------------"
                "---------------------------")+"\n")
        self.write("end_sandbox_summary")
        try:
            os.remove(self.__sandbox_log)
        except (IOError, OSError) as e:
            print("exception caught when cleansing sandbox_log=%s" % str(e))
        return 1

    def clear_preloaded_eclasses(self):
        if self.is_alive:
            self.write("clear_preloaded_eclasses")
            if not self.expect("clear_preload_eclasses succeeded", flush=True):
                self.shutdown_processor()
                return False
        self._preloaded_eclasses.clear()
        return True

    def preload_eclasses(self, cache, async=False, limited_to=None):
        """
        Preload an eclass stack's eclasses into bash functions.

        Avoids the cost of going to disk on inherit. Preloading eutils
        (which is heavily inherited) speeds up regen times for
        example.

        :param ec_file: filepath of eclass to preload
        :return: boolean, True for success
        """
        ec = cache.eclasses
        if limited_to:
            i = ((eclass, ec[eclass]) for eclass in limited_to)
        else:
            i = cache.eclasses.iteritems()
        for eclass, data in i:
            if data.path != self._preloaded_eclasses.get(eclass):
                if self._preload_eclass(data.path, async=True):
                    self._preloaded_eclasses[eclass] = data.path
        if not async:
            return self._consume_async_expects()
        return True

    def allow_eclass_caching(self):
        self._eclass_caching = True

    def disable_eclass_caching(self):
        self.clear_preloaded_eclasses()
        self._eclass_caching = False

    def _preload_eclass(self, ec_file, async=False):
        """
        Preload an eclass into a bash function.

        Avoids the cost of going to disk on inherit. Preloading eutils
        (which is heavily inherited) speeds up regen times for
        example.

        :param ec_file: filepath of eclass to preload
        :return: boolean, True for success
        """
        if not os.path.exists(ec_file):
            print("failed: %s" % ec_file)
            return False
        self.write("preload_eclass %s" % ec_file)
        if self.expect("preload_eclass succeeded", async=async, flush=True):
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

    locked = klass.alias_attr('processing_lock')

    @property
    def is_alive(self):
        """
        returns if it's known if the processor has been shutdown.

        Currently doesn't check to ensure the pid is still running,
        yet it should.
        """
        try:
            if self.pid is None:
                return False
            try:
                os.kill(self.pid, 0)
                return True
            except OSError:
                # pid is dead.
                pass
            self.pid = None
            return False

        except AttributeError:
            # thrown only if failure occurred instantiation.
            return False

    def shutdown_processor(self, ignore_keyboard_interrupt=False):
        """
        tell the daemon to shut itself down, and mark this instance as dead
        """
        try:
            if self.is_alive:
                self.write("shutdown_daemon", disable_runtime_exceptions=True)
                self.ebd_write.close()
                self.ebd_read.close()
            else:
                return
        except (EnvironmentError, ValueError):
            os.kill(self.pid, signal.SIGTERM)

        # now we wait.
        try:
            os.waitpid(self.pid, 0)
        except KeyboardInterrupt:
            if not ignore_keyboard_interrupt:
                raise

        # currently, this assumes all went well.
        # which isn't always true.
        self.pid = None

    def set_sandbox_state(self, state):
        """
        tell the daemon whether to enable the sandbox, or disable it
        :param state: boolean, if True enable sandbox
        """
        if state:
            self.write("set_sandbox_state 1")
        else:
            self.write("set_sandbox_state 0")

    def _generate_env_str(self, env_dict):
        data = []
        for key, val in env_dict.iteritems():
            if key in self.dont_export_vars:
                continue
            if not key[0].isalpha():
                raise KeyError("%s: bash doesn't allow digits as the first char" % (key,))
            if not isinstance(val, basestring):
                raise ValueError("_generate_env_str was fed a bad value; key=%s, val=%s"
                    % (key, val))
            if val.isalnum():
                data.append("%s=%s" % (key, val))
            elif "'" not in val:
                data.append("%s='%s'" % (key, val))
            else:
                data.append("%s=$'%s'" % (key, val.replace("'", "\\'")))
        return 'export %s' % (' '.join(data),)

    def send_env(self, env_dict, async=False, tmpdir=None):
        """
        transfer the ebuild's desired env (env_dict) to the running daemon

        :type env_dict: mapping with string keys and values.
        :param env_dict: the bash env.
        """
        data = self._generate_env_str(env_dict)
        old_umask = os.umask(0002)
        if tmpdir:
            path = pjoin(tmpdir, 'ebd-env-transfer')
            fileutils.write_file(path, 'wb', data)
            self.write("start_receiving_env file %s\n" % (path,),
                append_newline=False)
        else:
            self.write("start_receiving_env bytes %i\n%s" %
                (len(data), data), append_newline=False)
        os.umask(old_umask)
        return self.expect("env_received", async=async, flush=True)

    def set_logfile(self, logfile=''):
        """
        Set the logfile (location to log to).

        Relevant only when the daemon is sandbox'd,

        :param logfile: filepath to log to
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

    def _ensure_metadata_paths(self, paths):
        paths = tuple(paths)
        if self._metadata_paths == paths:
            return
        # filter here, so that a screwy default doesn't result in resetting it
        # every time.
        data = ':'.join(filter(None, paths))
        self.write("set_metadata_path %i\n%s" % (len(data), data),
            append_newline=False)
        if self.expect("metadata_path_received", flush=True):
            self._metadata_paths = paths

    def _run_depend_like_phase(self, command, package_inst, eclass_cache,
                               extra_commands={}):
        self._ensure_metadata_paths(const.HOST_NONROOT_PATHS)

        e = expected_ebuild_env(package_inst, depends=True)
        data = self._generate_env_str(e)
        self.write("%s %i\n%s" % (command, len(data), data),
            append_newline=False)

        updates = None
        if self._eclass_caching:
            updates = set()
        commands = extra_commands.copy()
        commands["request_inherit"] = partial(inherit_handler, eclass_cache, updates=updates)
        val = self.generic_handler(additional_commands=commands)

        if not val:
            logger.error("returned val from %s was '%s'" % (command, str(val)))
            raise Exception(val)

        if updates:
            self.preload_eclasses(eclass_cache, limited_to=updates, async=True)

    def get_ebuild_environment(self, package_inst, eclass_cache):
        """Request a dump of the ebuild environ for a package.

        This dump is created from doing metadata sourcing.

        :param package_inst: :obj:`pkgcore.ebuild.ebuild_src.package` instance
            to regenerate
        :param eclass_cache: :obj:`pkgcore.ebuild.eclass_cache` instance to use
            for eclass access
        :return: string of the ebuild environment.
        """

        environ = []
        def receive_env(self, line):
            if environ:
                raise InternalError(line, "receive_env was invoked twice.")
            line = line.strip()
            if not line:
                raise InternalError(line, "During env receive, ebd didn't give us a size.")
            elif not line.isdigit():
                raise InternalError(line, "Returned size wasn't an integer")
            # This is a raw transfer, for obvious reasons.
            environ.append(self.ebd_read.read(int(line)))

        self._run_depend_like_phase('gen_ebuild_env', package_inst, eclass_cache,
                                    {'receive_env': receive_env})
        if not environ:
            raise InternalError(None, "receive_env was never invoked.")
        # Dump any leading/trailing spaces.
        return environ[0].strip()

    def get_keys(self, package_inst, eclass_cache):
        """
        request the metadata be regenerated from an ebuild

        :param package_inst: :obj:`pkgcore.ebuild.ebuild_src.package` instance
            to regenerate
        :param eclass_cache: :obj:`pkgcore.ebuild.eclass_cache` instance to use
            for eclass access
        :return: dict when successful, None when failed
        """
        metadata_keys = {}
        def receive_key(self, line):
            line = line.split("=", 1)
            if len(line) != 2:
                raise FinishedProcessing(True)
            metadata_keys[line[0]] = line[1]

        self._run_depend_like_phase('gen_metadata', package_inst, eclass_cache,
                                    {"key": receive_key})

        return metadata_keys

    # this basically handles all hijacks from the daemon, whether
    # confcache or portageq.
    def generic_handler(self, additional_commands=None):
        """
        internal event handler responding to the running processor's requests.

        :type additional_commands: mapping from string to callable.
        :param additional_commands: Extra command handlers.
            Command names cannot have spaces.
            The callable is called with the processor as first arg, and
            remaining string (None if no remaining fragment) as second arg.
            If you need to split the args to command, whitespace splitting
            falls to your func.

        :raise UnhandledCommand: thrown when an unknown command is encountered.
        """

        # note that self is passed in. so... we just pass in the
        # unbound instance. Specifically, via digging through
        # __class__ if you don't do it, sandbox_summary (fex) cannot
        # be overridden, this func will just use this classes version.
        # so dig through self.__class__ for it. :P

        handlers = {"request_sandbox_summary":self.__class__.sandbox_summary}
        f = chuck_UnhandledCommand
        for x in ("prob", "env_receiving_failed", "failed"):
            handlers[x] = f
        del f

        handlers["phases"] = partial(
            chuck_StoppingCommand, lambda f: f.lower().strip() == "succeeded")

        handlers["killed"] = chuck_KeyboardInterrupt

        if additional_commands is not None:
            for x in additional_commands:
                if not callable(additional_commands[x]):
                    raise TypeError(additional_commands[x])

            handlers.update(additional_commands)

        self.lock()

        try:
            if self._outstanding_expects:
                if not self._consume_async_expects():
                    logger.error("error in daemon")
                    raise UnhandledCommand("expects out of alignment")
            while True:
                line = self.read().strip()
                # split on first whitespace.
                s = line.split(None, 1)
                if not s:
                    raise InternalError("Expected command; instead got nothing from %r" % (line,))
                if s[0] in handlers:
                    if len(s) == 1:
                        s.append(None)
                    handlers[s[0]](self, s[1])
                else:
                    logger.error("unhandled command '%s', line '%s'" %
                                 (s[0], line))
                    raise UnhandledCommand(line)

        except FinishedProcessing as fp:
            v = fp.val
            self.unlock()
            return v

def inherit_handler(ecache, ebp, line, updates=None):
    """
    Callback for implementing inherit digging into eclass_cache.

    Not for normal consumption.
    """
    if line is None:
        ebp.write("failed")
        raise UnhandledCommand(
            "inherit requires an eclass specified, none specified")

    line = line.strip()
    eclass = ecache.get_eclass(line)
    if eclass is None:
        ebp.write("failed")
        raise UnhandledCommand(
            "inherit requires an unknown eclass, %s cannot be found" % line)

    if eclass.path is not None:
        ebp.write("path")
        ebp.write(eclass.path)
    else:
        # XXX $10 this doesn't work.
        value = eclass.text_fileobj().read()
        ebp.write("transfer")
        ebp.write(value)

    if updates is not None:
        updates.add(line)


def expected_ebuild_env(pkg, d=None, env_source_override=None, depends=False):
    """
    setup expected ebuild vars

    :param d: if None, generates a dict, else modifies a passed in mapping
    :return: mapping
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
    if env_source_override:
        path = env_source_override.path
        if path is not None:
            d["EBUILD"] = path
    else:
        if pkg.ebuild.path is not None:
            d["EBUILD"] = pkg.ebuild.path
        else:
            # binpkgs don't have ebuild paths
            d["EBUILD"] = ""

    if not depends:
        path = list()
        path.extend(const.HOST_ROOT_PATHS)
        if "PKGCORE_SCRIPT_PATH" in os.environ:
            path.append(os.environ["PKGCORE_SCRIPT_PATH"])
        for eapi in range(0, pkg.eapi+1):
            eapi_helper_dir = pjoin(e_const.EBUILD_HELPERS_PATH, str(eapi))
            if os.path.exists(eapi_helper_dir):
                path.append(eapi_helper_dir)
        path.append(pjoin(e_const.EBUILD_HELPERS_PATH, "common"))
        path.extend(d.get("PATH", "").split(":"))
        d["PATH"] = ":".join(filter(None, path))
        d["PKGCORE_EAPI"] = pkg.eapi_obj.magic
        d["INHERITED"] = ' '.join(pkg.data.get("_eclasses_", ()))
        d["USE"] = ' '.join(str(x) for x in pkg.use)
        d["SLOT"] = pkg.fullslot

    for key in e_const.PKGCORE_DEBUG_VARS:
        val = os.environ.get(key)
        if val is not None:
            d[key] = val
    return d
