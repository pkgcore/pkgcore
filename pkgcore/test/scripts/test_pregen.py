# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import pregen
from pkgcore.test.scripts import helpers


class CommandlineTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pregen.OptionParser())
    main = staticmethod(pregen.main)

    def test_parser(self):
        self.assertError('Need a repository name.')
        self.assertError('I do not know what to do with more than 2 arguments',
                         '1', '2', '3')
        self.assertError('thread count needs to be at least 1', '1', '0')
        self.assertError("repo 'spork' was not found! known repos: ", 'spork')
