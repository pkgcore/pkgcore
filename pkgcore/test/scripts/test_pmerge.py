# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import pmerge
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
        livefs_repos = util.SimpleTree({'foo': {'bar': ('1')}})
        for cat in ('', 'spork/'):
            a = pmerge.parse_atom(parse_match('=%sfoon-1' % (cat,)), repo, livefs_repos)
            self.assertEqual(a.key, 'spork/foon')
            self.assertEqual([x.fullver for x in repo.itermatch(a)],
                ['1'])
            a = pmerge.parse_atom(parse_match('%sfoon' % (cat,)), repo, livefs_repos)
            self.assertEqual(a.key, 'spork/foon')
            self.assertEqual(sorted(x.fullver for x in repo.itermatch(a)),
                sorted(['1', '1.0.1', '2']))

        repo = util.SimpleTree({'spork': {'foon': ('1',)},
            'spork2': {'foon': ('2',)}})
        self.assertRaises(pmerge.NoMatches,
            pmerge.parse_atom, parse_match("foo"), repo, livefs_repos)
        self.assertRaises(pmerge.AmbiguousQuery,
            pmerge.parse_atom, parse_match("foon"), repo, livefs_repos)
        # test unicode conversion.
        a = pmerge.parse_atom(parse_match(u'=spork/foon-1'), repo, livefs_repos)
        self.assertEqual(a.key, 'spork/foon')
        self.assertTrue(isinstance(a.key, str))

        # test pkg name collisions between real and virtual pkgs on livefs
        # repos, the real pkg will be selected over the virtual
        livefs_repos = util.SimpleTree({'foo': {'bar': ('1')}, 'virtual': {'bar': ('0')}})
        repo = util.SimpleTree({'foo': {'bar': ('1',)}, 'virtual': {'bar': ('1',)}})
        a = pmerge.parse_atom(parse_match("bar"), repo, livefs_repos)
        self.assertEqual(a.key, 'foo/bar')
        self.assertTrue(isinstance(a.key, str))
