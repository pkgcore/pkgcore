# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

import cStringIO

from pkgcore.test import TestCase
from pkgcore.ebuild import filter_env


class NativeFilterEnvTest(TestCase):

    filter_env = staticmethod(filter_env.native_run)

    def get_output(self, raw_data, funcs=None, vars=None, invert_funcs=False,
                   invert_vars=False, debug=False):
        out = cStringIO.StringIO()
        if funcs:
            funcs = filter_env.build_regex_string(funcs)
        if vars:
            vars = filter_env.build_regex_string(vars)
        self.filter_env(out, raw_data, vars, funcs, invert_vars, invert_funcs)
        return out.getvalue()

    def test1(self):
        data = \
"""
MODULE_NAMES=${MODULE_NAMES//${i}(*};
tc-arch ()
{
    tc-ninja_magic_to_arch portage $@
}
"""
        self.assertIn('tc-arch', ''.join(
            self.get_output(data, vars='MODULE_NAMES')))
        self.assertNotIn('tc-arch', ''.join(
                self.get_output(data, funcs='tc-arch')))
        self.assertIn('tc-arch', ''.join(
                self.get_output(data, funcs='tc-arch', invert_funcs=True)))


class CPyFilterEnvTest(NativeFilterEnvTest):

    if filter_env.cpy_run is None:
        skip = 'cpy filter_env not available.'
    else:
        filter_env = staticmethod(filter_env.cpy_run)
