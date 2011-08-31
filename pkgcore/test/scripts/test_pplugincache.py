# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

from pkgcore.test import TestCase

from pkgcore import plugins
from pkgcore.scripts import pplugincache
from pkgcore.test.scripts import helpers

class CommandlineTest(TestCase, helpers.ArgParseMixin):

    _argparser = pplugincache.argparser

    has_config = False

    def test_parser(self):
        self.assertEqual([plugins], self.parse().packages)
