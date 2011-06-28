# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import pebuild
from pkgcore.test.scripts import helpers


class CommandlineTest(TestCase, helpers.ArgParseMixin):

    _argparser = pebuild.argparse_parser

    suppress_domain = True

    def test_parser(self):
        self.assertError('too few arguments')
        self.assertError('too few arguments', 'dev-util/diffball')
        self.assertError("argument atom: invalid atom value: 'spork'",
                         'spork', 'unpack')
        self.assertEqual(self.parse('foo/bar', 'baz', 'spork').phase, ['baz', 'spork'])
