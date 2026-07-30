import types

import pytest
from snakeoil.test.argparse_helpers import FakeStreamFormatter

from pkgcore.config import basics
from pkgcore.config.hint import ConfigHint, configurable
from pkgcore.scripts import pebuild
from pkgcore.test.misc import FakePkg, FakeRepo
from pkgcore.test.scripts.helpers import ArgParseMixin


class FakeDomain:
    pkgcore_config_type = ConfigHint(types={"repo": "ref:repo"}, typename="domain")

    def __init__(self, repo):
        object.__init__(self)
        self.ebuild_repos_unfiltered = repo


@configurable(typename="repo")
def fake_repo():
    pkgs = [
        FakePkg("app-arch/bzip2-1.0.1-r1", slot="0"),
        FakePkg("app-arch/bzip2-1.0.5-r2", slot="0"),
        FakePkg("sys-apps/coreutils-8.25", slot="0"),
        FakePkg("x11-libs/gtk+-2.24", slot="2"),
        FakePkg("x11-libs/gtk+-3.22", slot="3"),
    ]
    repo = FakeRepo(repo_id="gentoo", pkgs=pkgs)
    return repo


domain_config = basics.HardCodedConfigSection(
    {
        "class": FakeDomain,
        "repo": basics.HardCodedConfigSection({"class": fake_repo}),
        "default": True,
    }
)


class TestCommandline(ArgParseMixin):
    _argparser = pebuild.argparser

    def test_parser(self):
        self.assertError("the following arguments are required: target, phase")
        self.assertError(
            "the following arguments are required: phase", "dev-util/diffball"
        )

        # working initialization
        config = self.parse("sys-apps/coreutils", "bar", "baz", domain=domain_config)
        assert config.phase == ["bar", "baz"]


class _Stop(Exception):
    """Escape hatch: stops main() partway through and carries a message."""


def _raise(message, status=2):
    raise _Stop(message)


class TestMain:
    def _run(self, monkeypatch, pkgs):
        monkeypatch.setattr(
            pebuild.argparser, "err", FakeStreamFormatter(), raising=False
        )
        monkeypatch.setattr(pebuild.argparser, "error", _raise)
        options = types.SimpleNamespace(
            target=[("dev-python/pytest-qt-4.1.0", None)],
            domain=types.SimpleNamespace(
                build_pkg=lambda pkg, **kwargs: _raise(pkg.repo.location)
            ),
            repo=types.SimpleNamespace(match=lambda restriction, **kwargs: pkgs),
            debug=False,
            no_auto=False,
            phase=["compile"],
            verbosity=0,
        )
        pebuild.main(options, out=FakeStreamFormatter(), err=FakeStreamFormatter())

    def test_duplicate_repo_matches_prefers_local_checkout(self, tmp_path, monkeypatch):
        system_repo = tmp_path / "var-db-repos-gentoo"
        local_repo = tmp_path / "home-mgorny-git-gentoo"
        system_repo.mkdir()
        local_repo.mkdir()

        repo1 = FakeRepo(repo_id="gentoo", location=str(system_repo))
        repo2 = FakeRepo(repo_id="gentoo", location=str(local_repo))
        pkgs = [
            FakePkg("dev-python/pytest-qt-4.1.0", slot="0", repo=repo1),
            FakePkg("dev-python/pytest-qt-4.1.0", slot="0", repo=repo2),
        ]

        # run from within the local checkout, like `pebuild` invoked from a
        # dev clone that happens to share a repo_id with the configured repo
        monkeypatch.chdir(local_repo)

        with pytest.raises(_Stop) as excinfo:
            self._run(monkeypatch, pkgs)
        # build_pkg was reached (no "please refine" error) with the local pkg
        assert excinfo.value.args[0] == str(local_repo)

    def test_genuinely_ambiguous_matches_still_error(self, monkeypatch):
        repo1 = FakeRepo(repo_id="gentoo", location="/var/db/repos/gentoo")
        repo2 = FakeRepo(repo_id="other-overlay", location="/var/db/repos/other")
        pkgs = [
            FakePkg("dev-python/pytest-qt-4.1.0", slot="0", repo=repo1),
            FakePkg("dev-python/pytest-qt-4.1.0", slot="0", repo=repo2),
        ]

        with pytest.raises(_Stop, match="please refine"):
            self._run(monkeypatch, pkgs)
