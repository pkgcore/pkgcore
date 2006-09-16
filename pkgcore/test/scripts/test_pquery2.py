# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from twisted.trial import unittest

from pkgcore.scripts import pquery2
from pkgcore.test.scripts import helpers
from pkgcore.config import basics


class pquery2Test(unittest.TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pquery2.OptionParser())
    main = staticmethod(pquery2.main)

    def test_parser(self):
        self.assertError(
            '--noversion with --min or --max does not make sense.',
            '--noversion', '--max', '--min')
        self.assertTrue(self.parser.parse_args([]))

    def test_no_domain(self):
        self.assertErr(
            ['No default domain found, fix your configuration or '
             'pass --domain',
             'Valid domains: ',
             ],
            {})
