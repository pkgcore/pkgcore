# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import pmerge
from pkgcore.test.scripts import helpers
from pkgcore.repository import util
from pkgcore.ebuild import formatter
from pkgcore.config import basics, ConfigHint


default_formatter = basics.HardCodedConfigSection({
        'class': formatter.basic_factory,
        'default': True,
        })


class fake_domain(object):
    pkgcore_config_type = ConfigHint(typename='domain')
    def __init__(self):
        pass

default_domain = basics.HardCodedConfigSection({
    'class': fake_domain,
    'default': True,
    })

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
        # test unicode conversion.
        a = pmerge.parse_atom(u'=spork/foon-1', repo)
        self.assertEqual(a.key, 'spork/foon')
        self.assertTrue(isinstance(a.key, str))


class CommandlineTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pmerge.OptionParser())
    main = pmerge.main

    def test_parser(self):
        self.assertError(
            'No default formatter found, fix your configuration '
            'or pass --formatter (Valid formatters: spork)',
            spork=basics.HardCodedConfigSection({
                    'class': formatter.basic_factory}))
        self.assertError(
            "Using sets with -C probably isn't wise, aborting", '-Cs', 'boo',
            default_formatter=default_formatter, default_domain=default_domain)
        self.assertError(
            '--usepkg is redundant when --usepkgonly is used', '-Kk',
            default_formatter=default_formatter, default_domain=default_domain)
        self.assertError(
            "You must provide at least one atom", '--unmerge',
            default_formatter=default_formatter, default_domain=default_domain)
        options = self.parse('-s world', default_formatter=default_formatter,
            default_domain=default_domain)
        self.assertFalse(options.replace)
        options = self.parse('--clean', default_formatter=default_formatter,
            default_domain=default_domain)
        self.assertEqual(options.set, ['world', 'system'])
        self.assertTrue(options.deep, True)

        self.assertError(
            'No default domain found, fix your configuration or pass '
            '--domain (valid domains: )',
            default_formatter=default_formatter)
        self.assertError(
            'No default domain found, fix your configuration or pass '
            '--domain (valid domains: domain1)',
            default_formatter=default_formatter,
            domain1=basics.HardCodedConfigSection({'class':fake_domain}))
