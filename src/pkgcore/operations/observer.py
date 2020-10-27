__all__ = (
    "null_output", "formatter_output", "file_handle_output",
    "phase_observer", "repo_observer", "decorate_build_method",
)

import threading

from snakeoil import klass
from snakeoil.currying import pre_curry


def _convert(msg, args=(), kwds={}):
    # Note for interpolation, ValueError can be thrown by '%2(s'
    # TypeError by "%i" % "2", and KeyError via what you would expect.
    if args:
        if kwds:
            raise TypeError(
                "both position and optional args cannot be "
                "supplied: given msg(%r), args(%r), kwds(%r)"
                % (msg, args, kwds))
        try:
            return msg % args
        except (ValueError, TypeError) as e:
            raise TypeError(
                f"observer interpolation error: {e}, msg={msg!r}, args={args!r}")
    elif kwds:
        try:
            return msg % kwds
        except (KeyError, TypeError, ValueError) as e:
            raise TypeError(
                f"observer interpolation error: {e}, msg={msg!r}, kwds={kwds!r}")
    return msg


class null_output:

    def warn(self, msg, *args, **kwds):
        pass

    def error(self, msg, *args, **kwds):
        pass

    def info(self, msg, *args, **kwds):
        pass

    def debug(self, msg, *args, **kwds):
        pass

    def write(self, msg, *args, **kwds):
        pass

    def flush(self):
        pass


class formatter_output(null_output):

    def __init__(self, out):
        self._out = out
        self.verbosity = getattr(out, 'verbosity', 0)

    def debug(self, msg, *args, **kwds):
        self._out.write(_convert("debug: " + msg, args, kwds))

    def error(self, msg, *args, **kwds):
        prefixes = kwds.pop(
            'prefixes', (self._out.fg('red'), self._out.bold, ' * ', self._out.reset))
        self._out.write(_convert(msg, args, kwds), prefixes=prefixes)

    def info(self, msg, *args, **kwds):
        prefixes = kwds.pop(
            'prefixes', (self._out.fg('green'), self._out.bold, ' * ', self._out.reset))
        self._out.write(_convert(msg, args, kwds), prefixes=prefixes)

    def warn(self, msg, *args, **kwds):
        prefixes = kwds.pop(
            'prefixes', (self._out.fg('yellow'), self._out.bold, ' * ', self._out.reset))
        self._out.write(_convert(msg, args, kwds), prefixes=prefixes)

    def write(self, msg, *args, autoline=False, **kwds):
        self._out.write(_convert(msg, args, kwds), autoline=autoline)

    def flush(self):
        self._out.flush()


class file_handle_output(formatter_output):

    def debug(self, msg, *args, **kwds):
        self._out.write(f"debug: {_convert(msg, args, kwds)}\n")

    def error(self, msg, *args, **kwds):
        self._out.write(f"error: {_convert(msg, args, kwds)}\n")

    def info(self, msg, *args, **kwds):
        self._out.write(f"info: {_convert(msg, args, kwds)}\n")

    def warn(self, msg, *args, **kwds):
        self._out.write(f"warning: {_convert(msg, args, kwds)}\n")

    def write(self, msg, *args, **kwds):
        self._out.write(_convert(msg, args, kwds))


class phase_observer:

    def __init__(self, output, debug=False):
        self._output = output
        self.verbosity = getattr(output, 'verbosity', 0)
        self._debug = debug

    def phase_start(self, phase):
        if self._debug:
            self._output.write(f"starting {phase}\n")

    def debug(self, msg, *args, **kwds):
        if self._debug:
            self._output.debug(msg, *args, **kwds)

    info = klass.alias_attr("_output.info")
    warn = klass.alias_attr("_output.warn")
    error = klass.alias_attr("_output.error")
    write = klass.alias_attr("_output.write")
    flush = klass.alias_attr("_output.flush")

    def phase_end(self, phase, status):
        if self._debug:
            self._output.write(f"finished {phase}: {status}\n")


class repo_observer(phase_observer):

    def trigger_start(self, hook, trigger):
        if self._debug:
            self._output.write(f"hook {hook}: trigger: starting {trigger!r}\n", hook)

    def trigger_end(self, hook, trigger):
        if self._debug:
            self._output.write(f"hook {hook}: trigger: finished {trigger!r}\n", hook)

    def installing_fs_obj(self, obj):
        self._output.write(f">>> {obj}\n")

    def removing_fs_obj(self, obj):
        self._output.write(f"<<< {obj}\n")


def _reflection_func(attr, self, *args, **kwds):
    return self._invoke(attr, *args, **kwds)


def _mk_observer_proxy(target):
    class foo(target):
        for x in set(dir(target)).difference(dir(object)):
            locals()[x] = pre_curry(_reflection_func, x)
    return foo


class threadsafe_repo_observer(_mk_observer_proxy(repo_observer)):

    def __init__(self, observer):
        self._observer = observer
        self._lock = threading.Lock()

    def _invoke(self, attr, *args, **kwds):
        self._lock.acquire()
        try:
            return getattr(self._observer, attr)(*args, **kwds)
        finally:
            self._lock.release()


def wrap_build_method(phase, method, self, *args, **kwds):
    disable_observer = kwds.pop("disable_observer", False)
    if not hasattr(self.observer, 'phase_start') or disable_observer:
        return method(self, *args, **kwds)
    self.observer.phase_start(phase)
    ret = False
    try:
        ret = method(self, *args, **kwds)
    finally:
        self.observer.phase_end(phase, ret)
    return ret


def decorate_build_method(phase):
    def f(func):
        return pre_curry(wrap_build_method, phase, func)
    return f
