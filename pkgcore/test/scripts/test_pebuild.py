# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import pebuild
from pkgcore.test.scripts import helpers


class CommandlineTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pebuild.OptionParser())
    main = staticmethod(pebuild.main)

    def test_parser(self):
        self.assertError('Specify an atom and at least one phase.')
        self.assertError('Specify an atom and at least one phase.', 'foo')
        self.assertError("atom 'spork' is malformed: error spork",
                         'spork', 'unpack')
