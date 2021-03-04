from snakeoil.test import TestCase

from pkgcore.config import basics
from pkgcore.config.hint import ConfigHint, configurable
from pkgcore.ebuild import atom
from pkgcore.repository import util
from pkgcore.scripts import pquery
from pkgcore.test.scripts.helpers import ArgParseMixin


class FakeDomain:

    pkgcore_config_type = ConfigHint({'repos': 'refs:repo',
                                      'vdb': 'refs:repo'},
                                     typename='domain')

    def __init__(self, repos, vdb):
        object.__init__(self)
        self.source_repos = repos
        self.installed_repos = vdb


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


class CommandlineTest(TestCase, ArgParseMixin):

    _argparser = pquery.argparser

    def test_parser(self):
        self.assertError(
            'argument --min: not allowed with argument --max',
            '--max', '--min')
        self.parse('--all', domain=domain_config)

    def test_no_domain(self):
        self.assertError(
            "config error: no default object of type 'domain' found.  "
            "Please either fix your configuration, or set the domain via the --domain option.",
            '--all')

    def test_no_description(self):
        self.assertOut(
            [' * spork/foon-2',
             '     repo: MISSING',
             '     description: MISSING',
             '     homepage: MISSING',
             '     license: MISSING',
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
