# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.currying import pre_curry

class base(object):
    pass

class build_observer(object):

    def phase_start(self, phase):
        print "starting %s" % phase
        pass
    
    def phase_end(self, phase, status):
        print "finished %s: %s" % (phase, status)
        pass

def wrap_build_method(phase, method, self, *args, **kwds):
    if self.observer is None:
        return method(self, *args, **kwds)
    if not hasattr(self.observer, "phase_start"):
        import pdb;pdb.set_trace()
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
