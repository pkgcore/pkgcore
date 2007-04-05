# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from snakeoil.test import TestCase

from pkgcore.scripts import pquery
from pkgcore.test.scripts import helpers
from pkgcore.config import basics, ConfigHint, configurable
from pkgcore.repository import util
from pkgcore.ebuild import atom


class FakeDomain(object):

    pkgcore_config_type = ConfigHint({'repos': 'refs:repo',
                                      'vdb': 'refs:repo'},
                                     typename='domain')

    def __init__(self, repos, vdb):
        object.__init__(self)
        self.repos = repos
        self.vdb = vdb


@configurable(typename='repo')
def fake_repo():
    return util.SimpleTree({'spork': {'foon': ('1', '2')}})


@configurable(typename='repo')
def fake_vdb():
    return util.SimpleTree({})


domain_config = basics.HardCodedConfigSection({
        'class': FakeDomain,
        'repos': [basics.HardCodedConfigSection({'class': fake_repo})],
        'vdb': [basics.HardCodedConfigSection({'class': fake_vdb})],
        'default': True,
        })


class CommandlineTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pquery.OptionParser())
    main = staticmethod(pquery.main)

    def test_parser(self):
        self.assertError(
            '--no-version with --min or --max does not make sense.',
            '--no-version', '--max', '--min')
        self.parse('--all', domain=domain_config)

    def test_no_domain(self):
        self.assertError(
            'No default domain found, fix your configuration or '
            'pass --domain (Valid domains: )',
            '--all')

    def test_no_description(self):
        self.assertOut(
            [' * spork/foon-2',
             '     repo: MISSING',
             '     description: MISSING',
             '     homepage: MISSING',
             '',
             ],
            '-v', '--max', '--all',
            test_domain=domain_config)

    def test_atom(self):
        config = self.parse(
            '--print-revdep', 'a/spork', '--all', domain=domain_config)
        self.assertEqual([atom.atom('a/spork')], config.print_revdep)

    def test_no_contents(self):
        self.assertOut([], '--contents', '--all', test_domain=domain_config)
