# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import filter_env
from pkgcore.test.scripts import helpers


class CommandlineTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(filter_env.OptionParser())
    main = staticmethod(filter_env.main)

    def test_option_parser(self):
        self.assertError('-i cannot be specified twice',
                         '-i', __file__, '-i', 'bar')
        self.assertError(
            "error opening 'foo' ([Errno 2] No such file or directory: 'foo')",
            '-i', 'foo')
        options = self.parse('-Vf', 'spork,,foon', '-i', __file__)
        self.assertEqual(['spork', 'foon'], options.funcs)
        self.assertTrue(options.func_match)
        self.assertFalse(options.var_match)
