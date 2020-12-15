from snakeoil.test import TestCase

from pkgcore.config import basics
from pkgcore.config.hint import ConfigHint
from pkgcore.scripts import pclonecache
from pkgcore.test.scripts.helpers import ArgParseMixin


class Cache:

    pkgcore_config_type = ConfigHint(typename='cache')

    def __init__(self, readonly=True):
        self.readonly = self.frozen = readonly


class CommandlineTest(TestCase, ArgParseMixin):

    _argparser = pclonecache.argparser

    def test_parser(self):
        self.assertError(
            'the following arguments are required: target',
            'spork')
        self.assertError(
            "argument source: couldn't find cache 'spork'",
            'spork', 'spork2')
        self.assertError(
            "argument target: couldn't find cache 'spork2' (available: spork)",
            'spork', 'spork2',
            spork=basics.HardCodedConfigSection({'class': Cache}))
        self.assertError(
            "argument target: cache 'spork2' is readonly",
            'spork', 'spork2',
            spork=basics.HardCodedConfigSection({'class': Cache,}),
            spork2=basics.HardCodedConfigSection({'class': Cache,}))
