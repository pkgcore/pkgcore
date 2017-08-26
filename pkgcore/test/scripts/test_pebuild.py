# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

from pkgcore.config import basics, ConfigHint, configurable
from pkgcore.scripts import pebuild
from pkgcore.test.misc import FakePkg, FakeRepo
from pkgcore.test.scripts.helpers import ArgParseMixin

from snakeoil import compatibility
from snakeoil.test import TestCase


class FakeDomain(object):

    pkgcore_config_type = ConfigHint({'repo': 'ref:repo'}, typename='domain')

    def __init__(self, repo):
        object.__init__(self)
        self.ebuild_repos_raw = repo


@configurable(typename='repo')
def fake_repo():
    pkgs = [
        FakePkg('app-arch/bzip2-1.0.1-r1', slot='0'),
        FakePkg('app-arch/bzip2-1.0.5-r2', slot='0'),
        FakePkg('sys-apps/coreutils-8.25', slot='0'),
        FakePkg('x11-libs/gtk+-2.24', slot='2'),
        FakePkg('x11-libs/gtk+-3.22', slot='3'),
    ]
    repo = FakeRepo(repo_id='gentoo', pkgs=pkgs)
    return repo


domain_config = basics.HardCodedConfigSection({
        'class': FakeDomain,
        'repo': basics.HardCodedConfigSection({'class': fake_repo}),
        'default': True,
        })


class CommandlineTest(TestCase, ArgParseMixin):

    _argparser = pebuild.argparser

    def test_parser(self):
        if compatibility.is_py3k:
            self.assertError('the following arguments are required: <atom|ebuild>, phase')
            self.assertError('the following arguments are required: phase', 'dev-util/diffball')
        else:
            self.assertError('too few arguments')
            self.assertError('too few arguments', 'dev-util/diffball')

        self.assertError("no matches: 'foo/bar'", 'foo/bar', 'baz', 'spork', domain=domain_config)

        # select highest version of a package with multiple versions
        config = self.parse('app-arch/bzip2', 'baz', 'spork', domain=domain_config)
        self.assertEqual(config.pkg, FakePkg('app-arch/bzip2-1.0.5-r2'))

        # packages with multiple slots require a specific slot selection
        self.assertError("please refine your restriction to one match", 'x11-libs/gtk+', 'baz', 'spork', domain=domain_config)

        # working initialization
        config = self.parse('sys-apps/coreutils', 'bar', 'baz', domain=domain_config)
        self.assertEqual(config.phase, ['bar', 'baz'])
