# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

from snakeoil import compatibility

from pkgcore.scripts import pebuild
from pkgcore.test import TestCase
from pkgcore.test.scripts import helpers


class CommandlineTest(TestCase, helpers.ArgParseMixin):

    _argparser = pebuild.argparser

    suppress_domain = True

    def test_parser(self):
        if compatibility.is_py3k:
            self.assertError('the following arguments are required: <atom|ebuild>, phase')
            self.assertError('the following arguments are required: phase', 'dev-util/diffball')
        else:
            self.assertError('too few arguments')
            self.assertError('too few arguments', 'dev-util/diffball')
        self.assertEqual(self.parse('foo/bar', 'baz', 'spork').phase, ['baz', 'spork'])
