# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import pmerge
from pkgcore.test.scripts import helpers
from pkgcore.test.repository import util
from pkgcore.config import basics


class parse_atom_test(TestCase):

    def test_parse_atom(self):
        repo = util.SimpleTree({'spork': {'foon': ('1', '2')}})
        for cat in ('', 'spork/'):
            a = pmerge.parse_atom('=%sfoon-1' % (cat,), repo)
            self.assertEqual(a.cpvstr, 'spork/foon-1')
            self.assertEqual(a.op, '=')
            a = pmerge.parse_atom('%sfoon' % (cat,), repo)
            self.assertEqual(a.cpvstr, 'spork/foon')
            self.assertEqual(a.op, '')


class pmerge_test(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pmerge.OptionParser())
    main = pmerge.main

    def test_parser(self):
        self.assertError(
            "Sorry, using sets with -C probably isn't wise", '-Cs', 'boo')
        self.assertError(
            '--usepkg is redundant when --usepkgonly is used', '-Kk')
        self.assertError("need at least one atom", '--unmerge')
