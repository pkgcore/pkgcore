# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

__all__ = ("null_output", "formatter_output", "file_handle_output",
    "phase_observer", "build_observer", "repo_observer",
    "decorate_build_method")

from snakeoil.currying import pre_curry
from snakeoil import klass


def _convert(msg, args=(), kwds={}):
    if args:
        if kwds:
            raise TypeError("both position and optional args cannot be "
                "supplied: given msg(%r), args(%r), kwds(%r)"
                % (msg, args, kwds))
        return msg % args
    return msg % kwds


class null_output(object):

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


class formatter_output(null_output):

    def __init__(self, out):
        self._out = out

    def error(self, msg, *args, **kwds):
        self._out.error(_convert(msg, args, kwds))

    def info(self, msg, *args, **kwds):
        self._out.write(_convert(msg, args, kwds))

    def warn(self, msg, *args, **kwds):
        self._out.warn(_convert(msg, args, kwds))

    def write(self, msg, *args, **kwds):
        self._out.write(_convert(msg, args, kwds), autoline=False)


class file_handle_output(null_output):

    def __init__(self, out):
        self.out = out

    def info(self, msg, *args, **kwds):
        self._out.write("info: %s\n" % _convert(msg, args, kwds))

    def debug(self, msg, *args, **kwds):
        self._out.write("debug: %s\n" % _convert(msg, args, kwds))

    def warn(self, msg, *args, **kwds):
        self._out.write("warning: %s\n" % _convert(msg, args, kwds))

    def error(self, msg, *args, **kwds):
        self._out.write("error: %s\n" % _convert(msg, args, kwds))

    def write(self, msg, *args, **kwds):
        self._out.write(_convert(msg, args, kwds))


class phase_observer(object):

    def __init__(self, output, semiquiet=True):
        self._output = output
        self._semiquiet = semiquiet

    def phase_start(self, phase):
        if not self._semiquiet:
            self._output.write("starting %s\n" % phase)

    def debug(self, msg, *args, **kwds):
        if not self._semiquiet:
            self._output.debug(msg, *args, **kwds)

    info  = klass.alias_attr("_output.info")
    warn  = klass.alias_attr("_output.warn")
    error = klass.alias_attr("_output.error")
    write = klass.alias_attr("_output.write")

    def phase_end(self, phase, status):
        if not self._semiquiet:
            self._output.write("finished %s: %s\n" % (phase, status))

# left in place for compatibility sake
build_observer = phase_observer


class repo_observer(phase_observer):

    def trigger_start(self, hook, trigger):
        if not self._semiquiet:
            self._output.write("hook %s: trigger: starting %r\n" % (hook, trigger))

    def trigger_end(self, hook, trigger):
        if not self._semiquiet:
            self._output.write("hook %s: trigger: finished %r\n" % (hook, trigger))

    def installing_fs_obj(self, obj):
        self._output.write(">>> %s\n" % obj)

    def removing_fs_obj(self, obj):
        self._output.write("<<< %s\n" % obj)


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
