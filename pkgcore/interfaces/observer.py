# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.currying import pre_curry

class base(object):

    def warn(self, msg):
        pass


class phase_observer(object):

    def phase_start(self, phase):
        pass

    def phase_end(self, phase, status):
        pass


class file_phase_observer(phase_observer):

    def __init__(self, out, semiquiet=True):
        self._out = out
        self._semiquiet = semiquiet

    def phase_start(self, phase):
        self._out.write("starting %s\n" % phase)

    def info(self, msg):
        self._out.write("info: %s\n" % msg)

    def warn(self, msg):
        self._out.write("warning: %s\n" % msg)

    def phase_end(self, phase, status):
        if not self._semiquiet:
            self._out.write("finished %s: %s\n" % (phase, status))


class build_observer(base, phase_observer):
    pass


class repo_base(base):
    pass


class repo_observer(repo_base, phase_observer):

    def trigger_start(self, hook, trigger):
        pass

    trigger_end = trigger_start

    def installing_fs_obj(self, obj):
        pass

    removing_fs_obj = installing_fs_obj


class file_build_observer(build_observer, file_phase_observer):
    pass


class file_repo_observer(file_phase_observer, repo_base):

    def __init__(self, out, semiquiet=True):
        self._out = out
        self._semiquiet = semiquiet

    def trigger_start(self, hook, trigger):
        self._out.write("hook %s: trigger: starting %r\n" % (hook, trigger))

    def trigger_end(self, hook, trigger):
        if not self._semiquiet:
            self._out.write("hook %s: trigger: finished %r\n" % (hook, trigger))

    def installing_fs_obj(self, obj):
        self._out.write(">>> %s\n" % obj)

    def removing_fs_obj(self, obj):
        self._out.write("<<< %s\n" % obj)


def wrap_build_method(phase, method, self, *args, **kwds):
    disable_observer = kwds.pop("disable_observer", False)
    if self.observer is None or disable_observer:
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


