# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import pmerge
from pkgcore.test.scripts import helpers
from pkgcore.repository import util


class AtomParsingTest(TestCase):

    def test_parse_atom(self):
        repo = util.SimpleTree({'spork': {'foon': ('1', '1.0.1', '2')}})
        for cat in ('', 'spork/'):
            a = pmerge.parse_atom('=%sfoon-1' % (cat,), repo)
            self.assertEqual(a.key, 'spork/foon')
            self.assertEqual([x.fullver for x in repo.itermatch(a)],
                ['1'])
            a = pmerge.parse_atom('%sfoon' % (cat,), repo)
            self.assertEqual(a.key, 'spork/foon')
            self.assertEqual(sorted(x.fullver for x in repo.itermatch(a)),
                sorted(['1', '1.0.1', '2']))

        repo = util.SimpleTree({'spork': {'foon': ('1',)},
            'spork2': {'foon': ('2',)}})
        self.assertRaises(pmerge.NoMatches,
            pmerge.parse_atom, "foo", repo)
        self.assertRaises(pmerge.AmbiguousQuery,
            pmerge.parse_atom, "foon", repo)


class CommandlineTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pmerge.OptionParser())
    main = pmerge.main

    def test_parser(self):
        self.assertError(
            "Using sets with -C probably isn't wise, aborting", '-Cs', 'boo')
        self.assertError(
            '--usepkg is redundant when --usepkgonly is used', '-Kk')
        self.assertError("You must provide at least one atom", '--unmerge')
        options = self.parse('-s world')
        self.assertFalse(options.replace)
        options = self.parse('--clean')
        self.assertEqual(options.set, ['world', 'system'])
        self.assertTrue(options.deep, True)
