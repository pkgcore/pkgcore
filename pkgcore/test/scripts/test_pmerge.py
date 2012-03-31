# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import pmerge
from pkgcore.test.scripts import helpers
from pkgcore.repository import util
from pkgcore.ebuild import formatter
from pkgcore.config import basics
from pkgcore.util.parserestrict import parse_match


default_formatter = basics.HardCodedConfigSection({
        'class': formatter.basic_factory,
        'default': True,
        })


class AtomParsingTest(TestCase):

    def test_parse_atom(self):
        repo = util.SimpleTree({'spork': {'foon': ('1', '1.0.1', '2')}})
        for cat in ('', 'spork/'):
            a = pmerge.parse_atom(parse_match('=%sfoon-1' % (cat,)), repo)
            self.assertEqual(a.key, 'spork/foon')
            self.assertEqual([x.fullver for x in repo.itermatch(a)],
                ['1'])
            a = pmerge.parse_atom(parse_match('%sfoon' % (cat,)), repo)
            self.assertEqual(a.key, 'spork/foon')
            self.assertEqual(sorted(x.fullver for x in repo.itermatch(a)),
                sorted(['1', '1.0.1', '2']))

        repo = util.SimpleTree({'spork': {'foon': ('1',)},
            'spork2': {'foon': ('2',)}})
        self.assertRaises(pmerge.NoMatches,
            pmerge.parse_atom, parse_match("foo"), repo)
        self.assertRaises(pmerge.AmbiguousQuery,
            pmerge.parse_atom, parse_match("foon"), repo)
        # test unicode conversion.
        a = pmerge.parse_atom(parse_match(u'=spork/foon-1'), repo)
        self.assertEqual(a.key, 'spork/foon')
        self.assertTrue(isinstance(a.key, str))
