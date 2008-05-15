# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>: BSD/GPL2
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
        data = "f() {\n x \{}\n}\n"
        self.assertNotIn('}', ''.join(self.get_output(data, 'f')))


class CPyFilterEnvTest(NativeFilterEnvTest):

    if filter_env.cpy_run is None:
        skip = 'cpy filter_env not available.'
    else:
        filter_env = staticmethod(filter_env.cpy_run)
