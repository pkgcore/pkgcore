# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os

from pkgcore import spawn
from pkgcore.const import EBUILD_ENV_PATH

from pkgcore.test import TestCase, SkipTest

try:
    path = spawn.find_binary("filter-env", EBUILD_ENV_PATH)
except spawn.CommandNotFound:
    path = None    

from pkgcore.test.mixins import TempDirMixin

class TestFilterEnv(TempDirMixin, TestCase):

    if path is None:
        skip = "filter-env binary isn't available"

    filter_env_path = path
    
    @staticmethod
    def mangle_args(args):
        if isinstance(args, basestring):
            return [args]
        return args
    
    def get_output(self, raw_data, funcs=[], vars=[], invert_funcs=False,
        invert_vars=False, debug=False, gdb=False):

        args = [self.filter_env_path]
        if funcs:
            args.extend(("-f", ",".join(self.mangle_args(funcs))))
        if vars:
            args.extend(("-v", ",".join(self.mangle_args(vars))))
        if invert_funcs:
            args.append("-F")
        if invert_vars:
            args.append("-V")
        # rewrite this to avoid a temp file, using stdin instead.
        fp = os.path.join(self.dir, "data")
        open(fp, "w").write(raw_data)
        args.extend(("-i", fp))
        if debug or gdb:
            args.append("-dd")
        if gdb:
            spawn.spawn(["gdb", "--args"] + args + ["-ddd"])
        retval, data = spawn.spawn_get_output(args, collect_fds=(1,))
        self.assertEqual(retval, 0, "retval %i: %r\nargs: %r" %
            (retval, data, args))
        return data
    
    def test1(self):
	data = \
"""
MODULE_NAMES=${MODULE_NAMES//${i}(*};
tc-arch ()
{
    tc-ninja_magic_to_arch portage $@
}
"""
        self.assertIn('tc-arch', "".join(
            self.get_output(data, vars='MODULE_NAMES')))
