# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.test import TestCase

from pkgcore import plugins
from pkgcore.scripts import pplugincache
from pkgcore.test.scripts import helpers

class CommandlineTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pplugincache.OptionParser())
    main = staticmethod(pplugincache.main)

    def test_parser(self):
        self.assertEqual([plugins], self.parse().packages)
