import sys

import pytest
from snakeoil.test import TestCase

from pkgcore.config import basics, errors
from pkgcore.config.hint import configurable
from pkgcore.scripts import pconfig
from pkgcore.test.scripts.helpers import ArgParseMixin


@configurable({'reff': 'ref:spork'})
def spork(reff):
    """Test thing."""

def foon():
    pass

@configurable(typename='spork')
def pseudospork():
    pass

@configurable(typename='multi', allow_unknowns=True, types={
        'string': 'str', 'boolean': 'bool', 'list': 'list',
        'callable': 'callable', 'lazy_ref': 'lazy_ref:spork',
        'ref': 'ref:spork', 'lazy_refs': 'lazy_refs:spork',
        'refs': 'refs:spork',
        })
def multi(**kwargs):
    """Just something taking all kinds of args."""

# "in positional but not in required" is an error.
@configurable(positional=['foon'])
def broken_type(*args):
    """Noop."""

@configurable(types={'inc': 'list'}, allow_unknowns=True)
def increment(inc=()):
    """Noop."""


class DescribeClassTest(ArgParseMixin):

    _argparser = pconfig.describe_class

    def test_parser(self, capsys):
        self.assertError(
            'the following arguments are required: target_class')

        module = "module 'pkgcore'"

        with pytest.raises(SystemExit):
            self.parse('pkgcore.spork')
        captured = capsys.readouterr()
        assert captured.err.strip() == (
            f"argument target_class: Failed importing target 'pkgcore.spork': '{module} has no attribute 'spork''")

        with pytest.raises(SystemExit):
            self.parse('pkgcore.a', 'pkgcore.b')
        captured = capsys.readouterr()
        assert captured.err.strip() == (
            f"argument target_class: Failed importing target 'pkgcore.a': '{module} has no attribute 'a''")

        self.parse('pkgcore.scripts')

    def test_describe_class(self):
        self.assertOut(
            ['typename is spork',
             'Test thing.',
             '',
             'reff: ref:spork (required)'],
            'module.scripts.test_pconfig.spork')
        self.assertOut(
            ['typename is increment',
             'Noop.',
             'values not listed are handled as strings',
             '',
             'inc: list'],
            'module.scripts.test_pconfig.increment')

    def test_broken_type(self):
        self.assertErr(
            ['Not a valid type!'],
            'module.scripts.test_pconfig.broken_type')


class ClassesTest(TestCase, ArgParseMixin):

    _argparser = pconfig.classes

    def test_classes(self):
        sections = []
        for i in range(10):
            @configurable(typename='spork')
            def noop():
                """noop"""
            noop.__name__ = str(i)
            sections.append(basics.HardCodedConfigSection({'class': noop}))
        self.assertOut(
            ['module.scripts.test_pconfig.foon'],
            spork=basics.HardCodedConfigSection({'class': foon}))
        self.assertOut([
                'module.scripts.test_pconfig.0',
                'module.scripts.test_pconfig.1',
                'module.scripts.test_pconfig.2',
                'module.scripts.test_pconfig.3',
                'module.scripts.test_pconfig.4',
                'module.scripts.test_pconfig.5',
                'module.scripts.test_pconfig.multi',
                'module.scripts.test_pconfig.pseudospork',
                'module.scripts.test_pconfig.spork',
                ],
            bork=basics.HardCodedConfigSection({
                    'class': pseudospork, 'bork': True, 'inherit-only': True}),
            multi=basics.HardCodedConfigSection({
                    'class': multi,
                    'ref': sections[0],
                    'refs': sections[1:3],
                    'lazy_ref': sections[3],
                    'lazy_refs': sections[4:6],
                    'random': 'unknown',
                    }),
            spork=basics.HardCodedConfigSection({
                    'class': spork,
                    'reff': basics.HardCodedConfigSection({
                            'class': pseudospork})}))


class DumpTest(TestCase, ArgParseMixin):

    _argparser = pconfig.dump

    def test_dump(self):
        self.assertOut(
            ["'spork' {",
             '    # typename of this section: foon',
             '    class module.scripts.test_pconfig.foon;',
             '}',
             ''],
            spork=basics.HardCodedConfigSection({'class': foon}))

    def test_default(self):
        self.assertOut(
            ["'spork' {",
             '    # typename of this section: foon',
             '    class module.scripts.test_pconfig.foon;',
             '    default true;',
             '}',
             ''],
            spork=basics.HardCodedConfigSection({'class': foon,
                                                 'default': True}))

    def test_uncollapsable(self):
        self.assertOut(
            '',
            spork=basics.HardCodedConfigSection({
                    'class': foon, 'broken': True, 'inherit-only': True}))

    def test_serialise(self):
        nest = basics.HardCodedConfigSection({'class': pseudospork})
        self.assertOut(
            ["'spork' {",
             '    # typename of this section: multi',
             '    class module.scripts.test_pconfig.multi;',
             '    # type: bool',
             '    boolean True;',
             '    # type: callable',
             '    callable module.scripts.test_pconfig.multi;',
             '    # type: lazy_ref:spork',
             '    lazy_ref {',
             '        # typename of this section: spork',
             '        class module.scripts.test_pconfig.pseudospork;',
             '    };',
             '    # type: lazy_refs:spork',
             '    lazy_refs {',
             '        # typename of this section: spork',
             '        class module.scripts.test_pconfig.pseudospork;',
             '    } {',
             '        # typename of this section: spork',
             '        class module.scripts.test_pconfig.pseudospork;',
             '    };',
             '    # type: list',
             "    list 'a' 'b\\' \"c';",
             '    # type: ref:spork',
             '    ref {',
             '        # typename of this section: spork',
             '        class module.scripts.test_pconfig.pseudospork;',
             '    };',
             '    # type: refs:spork',
             '    refs {',
             '        # typename of this section: spork',
             '        class module.scripts.test_pconfig.pseudospork;',
             '    } {',
             '        # typename of this section: spork',
             '        class module.scripts.test_pconfig.pseudospork;',
             '    };',
             '    # type: str',
             '    string \'it is a "stringy" \\\'string\\\'\';',
             '    # type: str',
             "    unknown 'random';",
             '}',
             ''],
            spork=basics.HardCodedConfigSection({
                    'class': multi,
                    'string': 'it is a "stringy" \'string\'',
                    'boolean': True,
                    'list': ['a', 'b\' "c'],
                    'callable': multi,
                    'ref': nest,
                    'lazy_ref': nest,
                    'refs': [nest, nest],
                    'lazy_refs': [nest, nest],
                    'unknown': 'random',
                    }))

    def test_one_typename(self):
        self.assertOut(
            ["'spork' {",
             '    # typename of this section: spork',
             '    class module.scripts.test_pconfig.pseudospork;',
             '}',
             '',
             ],
            'spork',
            spork=basics.HardCodedConfigSection({'class': pseudospork}),
            foon=basics.HardCodedConfigSection({'class': foon}),
            )


class UncollapsableTest(TestCase, ArgParseMixin):

    _argparser = pconfig.uncollapsable

    def test_uncollapsable(self):
        self.assertOut(
            ["section foon:",
            " Collapsing section named 'foon'",
            " cannot collapse inherit-only section"
            "",
            "",
            "section spork:",
            " Collapsing section named 'spork'",
            " type module.scripts.test_pconfig.spork needs settings for 'reff'"
            "",
            "",
            ],
            spork=basics.HardCodedConfigSection({'class': spork}),
            foon=basics.HardCodedConfigSection({'class': spork,
                                                'inherit-only': True}),
            )


class ConfigurablesTest(TestCase, ArgParseMixin):

    _argparser = pconfig.configurables

    def test_configurables(self):
        self.assertError(
            'unrecognized arguments: bar',
            'foo', 'bar')


class WeirdSection(basics.ConfigSection):

    def __contains__(self, key):
        return key == 'sects'

    def keys(self):
        return ['sects']

    def render_value(self, central, name, arg_type):
        if name != 'sects':
            raise KeyError(name)
        if arg_type != 'repr':
            raise errors.ConfigurationError(f'{arg_type!r} unsupported')
        return 'refs', [
            ['spork', basics.HardCodedConfigSection({'foo': 'bar'})],
            None, None]


class DumpUncollapsedTest(TestCase, ArgParseMixin):

    _argparser = pconfig.dump_uncollapsed

    def test_dump_uncollapsed(self):
        self.assertOut(
            ['# Warning:',
             '# Do not copy this output to a configuration file directly,',
             '# because the types you see here are only guesses.',
             '# A value used as "list" in the collapsed config will often',
             '# show up as "string" here and may need to be converted',
             '# (for example from space-separated to comma-separated)',
             '# to work in a config file with a different format.',
             '',
             '********',
             'Source 1',
             '********',
             '',
             'foon',
             '====',
             '# type: callable',
             "'class' = module.scripts.test_pconfigspork",
             '# type: bool',
             "'inherit-only' = True",
             '# type: refs',
             "'refs' = ",
             '    nested section 1',
             '    ================',
             '    # type: str',
             "    'crystal' = 'clear'",
             '',
             '    nested section 2',
             '    ================',
             '    # type: refs',
             "    'sects.prepend' = ",
             '        nested section 1',
             '        ================',
             "        named section 'spork'",
             '',
             '        nested section 2',
             '        ================',
             '        # type: str',
             "        'foo' = 'bar'",
             '',
             '',
             '# type: list',
             "'seq' = 'a' 'b c'",
             '# type: str',
             "'str' = 'quote \\'\" unquote'",
             '',
             'spork',
             '=====',
             '# type: callable',
             "'class' = module.scripts.test_pconfigspork",
             '',
             ],
            spork=basics.HardCodedConfigSection({'class': spork}),
            foon=basics.HardCodedConfigSection({
                    'class': spork,
                    'inherit-only': True,
                    'refs': [
                        basics.HardCodedConfigSection({'crystal': 'clear'}),
                        WeirdSection(),
                        ],
                    'seq': ['a', 'b c'],
                    'str': 'quote \'" unquote',
                    }),
            )
