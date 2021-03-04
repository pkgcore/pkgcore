import pytest

from pkgcore.config import basics
from pkgcore.config.hint import ConfigHint, configurable
from pkgcore.ebuild.repo_objs import RepoConfig
from pkgcore.repository import multiplex
from pkgcore.scripts import pshowkw
from pkgcore.test.misc import FakeEbuildRepo, FakePkg
from pkgcore.test.scripts.helpers import ArgParseMixin


class FakeDomain:

    pkgcore_config_type = ConfigHint({'repos': 'refs:repo'}, typename='domain')

    def __init__(self, repos):
        self.all_ebuild_repos_raw = multiplex.tree(*repos)
        self.root = None

    def add_repo(self, *args, **kwargs):
        """stubbed"""

    def find_repo(self, *args, **kwargs):
        """stubbed"""


class FakeRepo(FakeEbuildRepo):

    pkgcore_config_type = ConfigHint({}, typename='repo')

    def __init__(self, repo_id='faker', arches=('amd64', 'x86', 'arm', 'arm64')):
        config = RepoConfig('nonexistent')
        object.__setattr__(config, 'known_arches', frozenset(arches))
        pkgs = [
            FakePkg('app-arch/bzip2-1.0.1-r1', repo=self, data={'SLOT': '0'}, keywords=('x86',)),
            FakePkg('app-arch/bzip2-1.0.5-r2', repo=self, data={'SLOT': '0'}, keywords=('x86',)),
            FakePkg('sys-apps/coreutils-8.25', repo=self, data={'SLOT': '0'}),
            FakePkg('x11-libs/gtk+-2.24', repo=self, data={'SLOT': '2'}, keywords=('amd64',)),
            FakePkg('x11-libs/gtk+-3.20', repo=self, data={'SLOT': '3'}, keywords=('amd64', 'x86')),
        ]
        super().__init__(repo_id=repo_id, pkgs=pkgs, config=config)


domain_config = basics.HardCodedConfigSection({
    'class': FakeDomain,
    'repos': [basics.HardCodedConfigSection({'class': FakeRepo})],
    'default': True,
})


class TestCommandline(ArgParseMixin):

    _argparser = pshowkw.argparser

    def test_unknown_arches(self, capsys):
        fake_repo = FakeRepo()
        ns_kwargs = {'color': False, 'selected_repo': fake_repo}
        with pytest.raises(SystemExit):
            self.parse('-a', 'unknown', domain=domain_config, ns_kwargs=ns_kwargs)
        captured = capsys.readouterr()
        assert captured.err.strip() == (
            "pshowkw: error: unknown arch: 'unknown' (choices: amd64, arm, arm64, x86)")

    def test_missing_target(self):
        self.assertError(
            'missing target argument and not in a supported repo',
            domain=domain_config)

    def test_no_matches(self):
        fake_repo = FakeRepo()
        ns_kwargs = {'color': False, 'selected_repo': fake_repo}
        self.assertErr(
            ["pshowkw: no matches for 'foo/bar'"], 'foo/bar',
            domain=domain_config, ns_kwargs=ns_kwargs)

    def test_collapsed(self):
        fake_repo = FakeRepo()
        ns_kwargs = {'color': False, 'selected_repo': fake_repo}
        self.assertOut(
            ["x86"], '-c', 'bzip2',
            domain=domain_config, ns_kwargs=ns_kwargs)
        self.assertOut(
            ["amd64 x86"], '-c', 'gtk+',
            domain=domain_config, ns_kwargs=ns_kwargs)

    def test_specified_arches(self):
        fake_repo = FakeRepo()
        ns_kwargs = {'color': False, 'selected_repo': fake_repo}
        # specifying arch to be shown
        self.assertOut(
            ["amd64"], '-c', 'gtk+', '-a', 'amd64',
            domain=domain_config, ns_kwargs=ns_kwargs)
        # disabling arch from being shown
        self.assertOut(
            ["amd64"], '-c', 'gtk+', '-a=-x86',
            domain=domain_config, ns_kwargs=ns_kwargs)
        # no keywords matching specified arches
        self.assertOut(
            [''], '-c', 'gtk+', '-a' 'arm',
            domain=domain_config, ns_kwargs=ns_kwargs)

    def test_tabular_default_output(self):
        fake_repo = FakeRepo()
        ns_kwargs = {'color': False, 'selected_repo': fake_repo}
        self.assertOut("""\
keywords for x11-libs/gtk+:
      a   a
      m   r   e s r
      d a m x a l e
      6 r 6 8 p o p
      4 m 4 6 i t o
-----------------------
 2.24 + o o o 0 2 faker
 3.20 + o o + 0 3 faker
""".splitlines(),
            'gtk+',
            domain=domain_config, ns_kwargs=ns_kwargs)

    def test_tabular_specified_arch(self):
        fake_repo = FakeRepo()
        ns_kwargs = {'color': False, 'selected_repo': fake_repo}
        self.assertOut("""\
keywords for x11-libs/gtk+:
      a
      m e s r
      d a l e
      6 p o p
      4 i t o
-----------------
 2.24 + 0 2 faker
 3.20 + 0 3 faker
""".splitlines(),
            '-a', 'amd64', 'gtk+',
            domain=domain_config, ns_kwargs=ns_kwargs)

    def test_tabular_disabled_arch(self):
        fake_repo = FakeRepo()
        ns_kwargs = {'color': False, 'selected_repo': fake_repo}
        self.assertOut("""\
keywords for x11-libs/gtk+:
      a
      m     e s r
      d a x a l e
      6 r 8 p o p
      4 m 6 i t o
---------------------
 2.24 + o o 0 2 faker
 3.20 + o + 0 3 faker
""".splitlines(),
            '-a=-arm64', 'gtk+',
            domain=domain_config, ns_kwargs=ns_kwargs)

    def test_tabular_custom_output_format(self):
        fake_repo = FakeRepo()
        ns_kwargs = {'color': False, 'selected_repo': fake_repo}
        self.assertOut("""\
keywords for x11-libs/gtk+:
      | amd64   | arm   | arm64   | x86   | eapi   | slot   | repo
------+---------+-------+---------+-------+--------+--------+--------
 2.24 | +       | o     | o       | o     | 0      | 2      | faker
 3.20 | +       | o     | o       | +     | 0      | 3      | faker
""".splitlines(),
            '-f', 'presto', 'gtk+',
            domain=domain_config, ns_kwargs=ns_kwargs)
