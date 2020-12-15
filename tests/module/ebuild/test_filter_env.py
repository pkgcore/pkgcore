import io
from functools import partial

from snakeoil.test import TestCase

from pkgcore.ebuild import filter_env


class TestFilterEnv(TestCase):

    filter_env = staticmethod(partial(filter_env.main_run))

    def get_output(self, raw_data, funcs=None, vars=None, preserve_funcs=False,
                   preserve_vars=False, debug=False, global_envvar_callback=None):
        out = io.BytesIO()
        if funcs:
            funcs = funcs.split(',')
        if vars:
            vars = vars.split(',')
        self.filter_env(out, raw_data, vars, funcs, preserve_vars, preserve_funcs,
            global_envvar_callback=global_envvar_callback)
        return out.getvalue().decode('utf-8')

    def test_function_foo(self):
        ret = ''.join(self.get_output("function foo() {:;}", funcs="foo"))
        self.assertEqual(ret, '')
        ret = ''.join(self.get_output("functionfoo() {:;}", funcs="foo"))
        self.assertEqual(ret, 'functionfoo() {:;}')

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
        data = "dar=${yar##.%}\nfoo() {\n:\n}\n"
        ret = ''.join(self.get_output(data, vars='dar'))
        self.assertNotIn('dar', ret)
        self.assertIn('foo', ret)

        data = \
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
            self.get_output(data, funcs='src_compile')))
        ret = ''.join(self.get_output(data, funcs='src_unpack'))
        self.assertIn('src_compile', ret)
        self.assertNotIn('src_unpack', ret)
        data = \
"""src_install() {
    local -f ${f##*=}
}

pkg_postinst() {
    :
}
"""
        self.assertNotIn('pkg_postinst',
            ''.join(self.get_output(data, funcs='pkg_postinst')))
        data = \
"""src_unpack() {
    fnames=$(scanelf -pyqs__uClibc_start_main -F%F#s)
}
src_compile() {
    :
}
"""
        self.assertIn('src_compile',
            ''.join(self.get_output(data, funcs='src_unpack')))

        data = \
"""findtclver() {
    [ "$(#i)" = "3" ]
}

pkg_setup() {
    :
}
"""
        self.assertIn('pkg_setup',
            ''.join(self.get_output(data, funcs='findtclver')))

    def test_here(self):
        data = \
"""
src_install() {
    cat >${D}/etc/modules.d/davfs2 <<EOF
alias char-major-67 coda
alias /dev/davfs*   coda
EOF
}

pkg_setup() {
    :
}
"""
        self.assertNotIn('pkg_setup', ''.join(self.get_output(data,
            funcs='pkg_setup')))

        data = \
"""
pkg_setup() {
        while read line; do elog "${line}"; done <<EOF
The default behaviour of tcsh has significantly changed starting from
version 6.14-r1.  In contrast to previous ebuilds, the amount of
customisation to the default shell's behaviour has been reduced to a
bare minimum (a customised prompt).
If you rely on the customisations provided by previous ebuilds, you will
have to copy over the relevant (now commented out) parts to your own
~/.tcshrc.  Please check all tcsh-* files in
/usr/share/doc/${P}/examples/ and include their behaviour in your own
configuration files.
The tcsh-complete file is not any longer sourced by the default system
scripts.
EOF
}

pkg_foo() {
    :
}
"""
        self.assertNotIn('pkg_foo', ''.join(self.get_output(data,
            funcs='pkg_foo')))

    def test_vars(self):
        data = \
"""
f() {
    x=$y
}

z() {
    :
}
"""
        self.assertIn('z', ''.join(self.get_output(data,
            funcs='f')))

        data = \
"""
f() {
    x="${y}"
}

z() {
    :
}
"""
        self.assertIn('z', ''.join(self.get_output(data,
            funcs='f')))

        data = \
"""src_compile() {
    $(ABI=foo get_libdir)
}

pkg_setup() {
    :
}
"""
        self.assertIn('pkg_setup', ''.join(self.get_output(data,
            funcs='src_compile')))

    def test_quoting(self):
        data = \
"""
pkg_postinst() {
    einfo " /bin/ls ${ROOT}etc/init.d/net.* | grep -v '/net.lo$' | xargs -n1 ln -sfvn net.lo"
}

pkg_setup() {
    :
}
"""
        self.assertIn('pkg_setup', ''.join(self.get_output(data,
            funcs='pkg_postinst')))

        data = \
"""src_unpack() {
    testExp=$'\177\105\114\106\001\001\001'
}

src_install() {
    :
}
"""
        self.assertIn('src_install', ''.join(self.get_output(data,
            funcs='src_unpack')))

    def test_arg_awareness(self):
        data = "f() {\n x \\{}\n}\n"
        self.assertNotIn('}', ''.join(self.get_output(data, 'f')))

    def test_print_vars(self):
        def assertVars(data, var_list, assert_func=self.assertEqual):
            l = []
            self.get_output(data, global_envvar_callback=l.append)
            assert_func(sorted(var_list), sorted(l))
        assertVars("f(){\nX=dar\n}", [])
        assertVars("f(){\nX=dar\n}\nY=a", ['Y'])
        assertVars("f(){\nX=dar\n}\nmy command\nY=a\nf=$(dar)", ['Y', 'f'])
        assertVars("f(){\nX=dar\n}\nmy command\nY=a\nf=$(dar) foon\n", ['Y'],
            self.assertNotEqual)
        assertVars("f(){\nX=dar foon\n}\nY=dar\nf2(){Z=dar;}\n", ['Y'])
