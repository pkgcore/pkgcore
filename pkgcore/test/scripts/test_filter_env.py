# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import filter_env
from pkgcore.test.scripts import helpers


class CommandlineTest(TestCase, helpers.ArgParseMixin):

    _argparser = filter_env.argparser

    def test_option_parser(self):
        self.assertError(
            "argument --input/-i: can't open 'foo': [Errno 2] No such file or directory: 'foo'",
            '-i', 'foo')
        options = self.parse('-Vf', 'spork,,foon', '-i', __file__)
        self.assertEqual(['spork', 'foon'], options.funcs)
        self.assertFalse(options.func_match)
        self.assertTrue(options.var_match)

    def test_print_vars(self):
        raise AssertionError()

    test_print_vars.todo = "do it..."
