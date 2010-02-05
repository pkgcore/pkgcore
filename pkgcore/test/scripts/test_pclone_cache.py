# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import pclone_cache
from pkgcore.test.scripts import helpers
from pkgcore.config import basics, ConfigHint


class Cache(object):

    pkgcore_config_type = ConfigHint(typename='cache')

    def __init__(self, readonly=True):
        self.readonly = readonly


class CommandlineTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pclone_cache.OptionParser())
    main = staticmethod(pclone_cache.main)

    def test_parser(self):
        self.assertError(
            'Need two arguments: cache label to read from and '
            'cache label to write to.', 'spork')
        self.assertError(
            "read cache label 'spork' isn't defined.", 'spork', 'spork2')
        self.assertError(
            "write cache label 'spork2' isn't defined.",
            'spork', 'spork2',
            spork=basics.HardCodedConfigSection({'class': Cache}))
        self.assertError(
            "can't update cache label 'spork2', it's marked readonly.",
            'spork', 'spork2',
            spork=basics.HardCodedConfigSection({'class': Cache,}),
            spork2=basics.HardCodedConfigSection({'class': Cache,}))
