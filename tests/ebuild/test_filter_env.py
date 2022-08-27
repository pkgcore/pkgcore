import io
import textwrap

import pytest
from pkgcore.ebuild.filter_env import main_run


class TestFilterEnv:

    def get_output(self, raw_data, funcs=None, vars=None, preserve_funcs=False,
                   preserve_vars=False, debug=False, global_envvar_callback=None):
        out = io.BytesIO()
        if funcs:
            funcs = funcs.split(',')
        if vars:
            vars = vars.split(',')
        main_run(out, raw_data, vars, funcs, preserve_vars, preserve_funcs,
            global_envvar_callback=global_envvar_callback)
        return out.getvalue().decode('utf-8')

    def test_function_foo(self):
        ret = ''.join(self.get_output("function foo() {:;}", funcs="foo"))
        assert ret == ''
        ret = ''.join(self.get_output("functionfoo() {:;}", funcs="foo"))
        assert ret == 'functionfoo() {:;}'

    def test_simple(self):
        data = textwrap.dedent("""\
            foo() {
                :
            }

            bar() {
                :
            }
        """)
        ret = ''.join(self.get_output(data))
        assert 'foo' in ret
        assert 'bar' in ret
        ret = ''.join(self.get_output(data, funcs='foo'))
        assert 'foo' not in ret
        assert 'bar' in ret
        ret = ''.join(self.get_output(data, funcs='bar'))
        assert 'foo' in ret
        assert 'bar' not in ret
        ret = ''.join(self.get_output(data, funcs='bar,foo'))
        assert 'foo' not in ret
        assert 'bar' not in ret

    def test1(self):
        data = textwrap.dedent("""\
            MODULE_NAMES=${MODULE_NAMES//${i}(*};
            tc-arch ()
            {
                tc-ninja_magic_to_arch portage $@
            }
        """)
        ret = ''.join(self.get_output(data, vars='MODULE_NAMES'))
        assert 'MODULE_NAMES' not in ret
        assert 'tc-arch' in ret

    def test_comments(self):
        data = "dar=${yar##.%}\nfoo() {\n:\n}\n"
        ret = ''.join(self.get_output(data, vars='dar'))
        assert 'dar' not in ret
        assert 'foo' in ret

        data = textwrap.dedent("""\
            src_unpack() {
                use idn && {
                # BIND 9.4.0 doesn't have this patch
                :
                }
            }

            src_compile() {
                :
            }
        """)
        assert 'src_unpack' in ''.join(self.get_output(data, funcs='src_compile'))
        ret = ''.join(self.get_output(data, funcs='src_unpack'))
        assert 'src_compile' in ret
        assert 'src_unpack' not in ret
        data = textwrap.dedent("""\
            src_install() {
                local -f ${f##*=}
            }

            pkg_postinst() {
                :
            }
        """)
        assert 'pkg_postinst' not in ''.join(self.get_output(data, funcs='pkg_postinst'))
        data = textwrap.dedent("""\
            src_unpack() {
                fnames=$(scanelf -pyqs__uClibc_start_main -F%F#s)
            }
            src_compile() {
                :
            }
        """)
        assert 'src_compile' in ''.join(self.get_output(data, funcs='src_unpack'))

        data = textwrap.dedent("""\
            findtclver() {
                [ "$(#i)" = "3" ]
            }

            pkg_setup() {
                :
            }
        """)
        assert 'pkg_setup' in ''.join(self.get_output(data, funcs='findtclver'))

    def test_here(self):
        data = textwrap.dedent("""\
            src_install() {
                cat >${D}/etc/modules.d/davfs2 <<EOF
            alias char-major-67 coda
            alias /dev/davfs*   coda
            EOF
            }

            pkg_setup() {
                :
            }
        """)
        assert 'pkg_setup' not in ''.join(self.get_output(data, funcs='pkg_setup'))

        data = textwrap.dedent("""\
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
        """)
        assert 'pkg_foo' not in ''.join(self.get_output(data, funcs='pkg_foo'))

    def test_vars(self):
        data = textwrap.dedent("""\
            f() {
                x=$y
            }

            z() {
                :
            }
        """)
        assert 'z' in ''.join(self.get_output(data, funcs='f'))

        data = textwrap.dedent("""\
            f() {
                x="${y}"
            }

            z() {
                :
            }
        """)
        assert 'z' in ''.join(self.get_output(data, funcs='f'))

        data = textwrap.dedent("""\
            src_compile() {
                $(ABI=foo get_libdir)
            }

            pkg_setup() {
                :
            }
        """)
        assert 'pkg_setup' in ''.join(self.get_output(data, funcs='src_compile'))

    def test_quoting(self):
        data = textwrap.dedent("""\
            pkg_postinst() {
                einfo " /bin/ls ${ROOT}etc/init.d/net.* | grep -v '/net.lo$' | xargs -n1 ln -sfvn net.lo"
            }

            pkg_setup() {
                :
            }
        """)
        assert 'pkg_setup' in ''.join(self.get_output(data, funcs='pkg_postinst'))

        data = textwrap.dedent("""\
            src_unpack() {
                testExp=$'\177\105\114\106\001\001\001'
            }

            src_install() {
                :
            }
        """)
        assert 'src_install' in ''.join(self.get_output(data, funcs='src_unpack'))

    def test_arg_awareness(self):
        data = "f() {\n x \\{}\n}\n"
        assert '}' not in ''.join(self.get_output(data, 'f'))

    @pytest.mark.parametrize(("data", "var_list"), (
        ("f(){\nX=dar\n}", set()),
        ("f(){\nX=dar\n}\nY=a", {'Y'}),
        ("f(){\nX=dar\n}\nmy command\nY=a\nf=$(dar)", {'Y', 'f'}),
        ("f(){\nX=dar\n}\nmy command\nY=a\nf=$(dar) foon\n", {'Y', 'f'}),
        ("f(){\nX=dar foon\n}\nY=dar\nf2(){Z=dar;}\n", {'Y'})
    ))
    def test_print_vars(self, data, var_list):
        l = set()
        self.get_output(data, global_envvar_callback=l.add)
        assert var_list == l
