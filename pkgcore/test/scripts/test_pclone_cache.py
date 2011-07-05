# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import pclone_cache
from pkgcore.test.scripts import helpers
from pkgcore.config import basics, ConfigHint


class Cache(object):

    pkgcore_config_type = ConfigHint(typename='cache')

    def __init__(self, readonly=True):
        self.readonly = self.frozen = readonly


class CommandlineTest(TestCase, helpers.ArgParseMixin):

    _argparser = pclone_cache.argparse_parser

    def test_parser(self):
        self.assertError(
            'too few arguments',
            'spork')
        self.assertError(
            "argument source: couldn't find cache 'spork'",
            'spork', 'spork2')
        self.assertError(
            "argument target: couldn't find cache 'spork2'",
            'spork', 'spork2',
            spork=basics.HardCodedConfigSection({'class': Cache}))
        self.assertError(
            "argument target: cache 'spork2' is readonly",
            'spork', 'spork2',
            spork=basics.HardCodedConfigSection({'class': Cache,}),
            spork2=basics.HardCodedConfigSection({'class': Cache,}))
