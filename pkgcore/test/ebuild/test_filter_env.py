# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

import cStringIO

from pkgcore.test import TestCase
from pkgcore.ebuild import filter_env


class NativeFilterEnvTest(TestCase):

    filter_env = staticmethod(filter_env.native_run)

    def get_output(self, raw_data, funcs=None, vars=None, preserve_funcs=False,
                   preserve_vars=False, debug=False):
        out = cStringIO.StringIO()
        if funcs:
            funcs = filter_env.build_regex_string(funcs.split(','))
        if vars:
            vars = filter_env.build_regex_string(vars.split(','))
        self.filter_env(out, raw_data, vars, funcs, not preserve_vars, not preserve_funcs)
        return out.getvalue()

    def test_simple(self):
        data = \
"""
foo() {
    :
}

bar() {
    :
}
"""
        ret = ''.join(self.get_output(data))
        self.assertIn('foo', ret)
        self.assertIn('bar', ret)
        ret = ''.join(self.get_output(data, funcs='foo'))
        self.assertNotIn('foo', ret)
        self.assertIn('bar', ret)
        ret = ''.join(self.get_output(data, funcs='bar'))
        self.assertIn('foo', ret)
        self.assertNotIn('bar', ret)
        ret = ''.join(self.get_output(data, funcs='bar,foo'))
        self.assertNotIn('foo', ret)
        self.assertNotIn('bar', ret)

    def test1(self):
        data = \
"""
MODULE_NAMES=${MODULE_NAMES//${i}(*};
tc-arch ()
{
    tc-ninja_magic_to_arch portage $@
}
"""
        ret = ''.join(self.get_output(data, vars='MODULE_NAMES'))
        self.assertNotIn('MODULE_NAMES', ret)
        self.assertIn('tc-arch', ret)

    def test_comments(self):
        data1 = \
"""
src_unpack() {
    use idn && {
       # BIND 9.4.0 doesn't have this patch
       :
    }
}

src_compile() {
    :
}
"""
        self.assertIn('src_unpack', ''.join(
            self.get_output(data1, funcs='src_compile')))
        ret = ''.join(self.get_output(data1, funcs='src_unpack'))
        self.assertIn('src_compile', ret)
        self.assertNotIn('src_unpack', ret)

        data2 = "dar=${yar##.%}\nfoo() {\n:\n}\n"
        ret = ''.join(self.get_output(data2, vars='dar'))
        self.assertNotIn('dar', ret)
        self.assertIn('foo', ret)


class CPyFilterEnvTest(NativeFilterEnvTest):

    if filter_env.cpy_run is None:
        skip = 'cpy filter_env not available.'
    else:
        filter_env = staticmethod(filter_env.cpy_run)
