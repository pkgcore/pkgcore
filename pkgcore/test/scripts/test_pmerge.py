# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from twisted.trial import unittest

from pkgcore.scripts import pmerge
from pkgcore.test.scripts import helpers
from pkgcore.config import basics


class pquery2Test(unittest.TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pmerge.OptionParser())
    main = pmerge.main

    def test_parser(self):
        self.assertError(
            "Sorry, using sets with -C probably isn't wise", '-Cs', 'boo')
        self.assertError(
            '--usepkg is redundant when --usepkgonly is used', '-Kk')
        self.assertError("need at least one atom", '--unmerge')
