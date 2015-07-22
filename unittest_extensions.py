# Copyright: 2008-2011 Brian Harring <ferringb@gmail.com>
# License: BSD/GPL2

import os
import sys

import unittest


class TestLoader(unittest.TestLoader):

    """Test loader that knows how to recurse packages."""

    def __init__(self, blacklist):
        self.blacklist = blacklist
        unittest.TestLoader.__init__(self)

    def loadTestsFromModule(self, module):
        """Recurses if module is actually a package."""
        paths = getattr(module, '__path__', None)
        tests = [unittest.TestLoader.loadTestsFromModule(self, module)]
        if paths is None:
            # Not a package.
            return tests[0]
        if module.__name__ in self.blacklist:
            return tests[0]
        for path in paths:
            for child in os.listdir(path):
                if (child != '__init__.py' and child.endswith('.py') and
                        child.startswith('test')):
                    # Child module.
                    childname = '%s.%s' % (module.__name__, child[:-3])
                else:
                    childpath = os.path.join(path, child)
                    if not os.path.isdir(childpath):
                        continue
                    if not os.path.exists(os.path.join(childpath,
                                                       '__init__.py')):
                        continue
                    # Subpackage.
                    childname = '%s.%s' % (module.__name__, child)
                tests.append(self.loadTestsFromName(childname))
        return self.suiteClass(tests)

def protect_env(functor):
    def f(*args, **kwds):
        backup_env = os.environ.copy()
        backup_sys_path = sys.path[:]
        backup_sys_modules = sys.modules.copy()
        try:
            return functor(*args, **kwds)
        finally:
            os.environ.clear()
            os.environ.update(backup_env)
            sys.modules.clear()
            sys.modules.update(backup_sys_modules)
            sys.path[:] = backup_sys_path
    f.__name__ = functor.__name__
    f.__doc__ = functor.__doc__
    return f

@protect_env
def run_tests(namespaces, disable_fork=False, pythonpath=None,
              modules_to_wipe=(), blacklist=()):
    """a simple wrapper around unittest.main

    Primary benefit of this is wrapping unittest.main to protect
    the invoking env from modification where possible, including
    forking.
    """

    if disable_fork:
        pid = 0
    else:
        sys.stderr.flush()
        sys.stdout.flush()
        pid = os.fork()
    if pythonpath is not None:
        sys.path[:] = list(pythonpath)
    os.environ["PYTHONPATH"] = ":".join(sys.path)
    for module in modules_to_wipe:
        sys.modules.pop(module, None)

    if not pid:
        if not disable_fork:
            # thank you for binding freaking sys.stderr into your prototype
            # unittest...
            sys.stderr.flush()
            os.dup2(sys.stdout.fileno(), sys.stderr.fileno())

        args = ['setup.py', '-v']
        args.extend(namespaces)
        unittest.main(None, argv=args, testLoader=TestLoader(blacklist))
        if not disable_fork:
            os._exit(1)
        return

    retval = os.waitpid(pid, 0)[1]
    # exit code, else the signal.
    if retval >> 8:
        return retval >> 8
    return retval & 0xff

if __name__ == '__main__':
    sys.exit(run_tests(sys.argv[1:], disable_fork=True))
