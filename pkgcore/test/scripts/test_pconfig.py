# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from twisted.trial import unittest

from pkgcore.scripts import pconfig
from pkgcore.test.scripts import helpers
from pkgcore.config import configurable, basics

@configurable({'reff': 'ref:spork'})
def spork(reff):
    """Test thing."""

def foon():
    pass


class pconfigTest(unittest.TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pconfig.OptionParser())
    main = staticmethod(pconfig.main)

    def test_parser(self):
        options, args = self.parser.parse_args(['--dump'])
        self.assertTrue(options.dump)
        self.assertError(
            'specify only one mode please', '--uncollapsable', '--dump')
        self.assertError('nothing to do!')
        self.assertError(
            "Failed importing target 'pkgcore.spork': "
            "''module' object has no attribute 'spork''", '--describe-class',
            'pkgcore.spork')

    def test_describe_class(self):
        self.assertOut(
            ['typename is spork',
             '',
             'reff: ref:spork (required)'],
            {}, '--describe-class', 'pkgcore.test.scripts.test_pconfig.spork')

    def test_classes(self):
        self.assertOut(
            ['pkgcore.test.scripts.test_pconfig.foon'],
            {'spork': basics.HardCodedConfigSection({'class': foon})},
            '--classes')

    def test_dump(self):
        self.assertOut(
            ["'spork' {",
             '    # typename of this section: foon',
             '    class pkgcore.test.scripts.test_pconfig.foon;',
             '}',
             ''],
            {'spork': basics.HardCodedConfigSection({'class': foon})},
            '--dump')

    def test_uncollapsable(self):
        self.assertOut(
            ["Collapsing section named 'spork':",
             'type pkgcore.test.scripts.test_pconfig.spork needs settings for '
             "'reff'",
             ''],
            {'spork': basics.HardCodedConfigSection({'class': spork})},
            '--uncollapsable')
