# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import pconfig
from pkgcore.test.scripts import helpers
from pkgcore.config import configurable, basics
from pkgcore.util import commandline

@configurable({'reff': 'ref:spork'})
def spork(reff):
    """Test thing."""

def foon():
    pass

@configurable(typename='spork')
def pseudospork():
    pass


class DescribeClassTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pconfig.DescribeClassParser())
    main = staticmethod(pconfig.describe_class_main)

    def test_parser(self):
        self.assertError(
            "Failed importing target 'pkgcore.spork': "
            "''module' object has no attribute 'spork''", 'pkgcore.spork')
        self.assertError(
            'need exactly one argument: class to describe.')
        self.assertError(
            'need exactly one argument: class to describe.', 'a', 'b')

    def test_describe_class(self):
        self.assertOut(
            ['typename is spork',
             'Test thing.',
             '',
             'reff: ref:spork (required)'],
            'pkgcore.test.scripts.test_pconfig.spork')


class ClassesTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(commandline.OptionParser())
    main = staticmethod(pconfig.classes_main)

    def test_classes(self):
        self.assertOut(
            ['pkgcore.test.scripts.test_pconfig.foon'],
            spork=basics.HardCodedConfigSection({'class': foon}))
        self.assertOut(
            ['pkgcore.test.scripts.test_pconfig.pseudospork',
             'pkgcore.test.scripts.test_pconfig.spork'],
            spork=basics.HardCodedConfigSection({
                    'class': spork,
                    'reff': basics.HardCodedConfigSection({
                            'class': pseudospork})}))


class DumpTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pconfig.DumpParser())
    main = staticmethod(pconfig.dump_main)

    def test_dump(self):
        self.assertOut(
            ["'spork' {",
             '    # typename of this section: foon',
             '    class pkgcore.test.scripts.test_pconfig.foon;',
             '}',
             ''],
            spork=basics.HardCodedConfigSection({'class': foon}))

    def test_default(self):
        self.assertOut(
            ["'spork' {",
             '    # typename of this section: foon',
             '    class pkgcore.test.scripts.test_pconfig.foon;',
             '    default true;',
             '}',
             ''],
            spork=basics.HardCodedConfigSection({'class': foon,
                                                 'default': True}))

class UncollapsableTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(commandline.OptionParser())
    main = staticmethod(pconfig.uncollapsable_main)

    def test_uncollapsable(self):
        self.assertOut(
            ["Collapsing section named 'spork':",
             'type pkgcore.test.scripts.test_pconfig.spork needs settings for '
             "'reff'",
             ''],
            spork=basics.HardCodedConfigSection({'class': spork}))


class ConfigurablesTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pconfig.ConfigurablesParser())
    main = staticmethod(pconfig.configurables_main)

    def test_configurables(self):
        self.assertError(
            'pass at most one typename',
            'foo', 'bar')
