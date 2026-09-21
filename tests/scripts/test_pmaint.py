import os
from functools import partial
from io import BytesIO

import pytest
from snakeoil.formatters import PlainTextFormatter
from snakeoil.mappings import AttrAccessible

from pkgcore.config import basics
from pkgcore.config.hint import ConfigHint
from pkgcore.ebuild import overlays
from pkgcore.exceptions import PkgcoreUserException
from pkgcore.operations.repo import install, operations, replace, uninstall
from pkgcore.repository import syncable, util
from pkgcore.scripts import pmaint
from pkgcore.sync import base
from pkgcore.test.misc import FakePkg
from pkgcore.test.scripts.helpers import ArgParseMixin

Options = AttrAccessible


class fake_operations(operations):
    def _cmd_implementation_install(self, pkg, observer):
        self.repo.installed.append(pkg)
        return derive_op("add_data", install, self.repo, pkg, observer)

    def _cmd_implementation_uninstall(self, pkg, observer):
        self.repo.uninstalled.append(pkg)
        return derive_op("remove_data", uninstall, self.repo, pkg, observer)

    def _cmd_implementation_replace(self, oldpkg, newpkg, observer):
        self.repo.replaced.append((oldpkg, newpkg))
        return derive_op(
            ("add_data", "remove_data"), replace, self.repo, oldpkg, newpkg, observer
        )


class FakeRepo(util.SimpleTree):
    operations_kls = fake_operations

    def __init__(
        self, data, frozen=False, livefs=False, repo_id=None, location="/fake"
    ):
        self.installed = []
        self.replaced = []
        self.uninstalled = []
        super().__init__(
            data, pkg_klass=partial(FakePkg.for_tree_usage, repo=self), repo_id=repo_id
        )
        self.livefs = livefs
        self.frozen = frozen
        self.location = location


def make_repo_config(repo_data, livefs=False, frozen=False, repo_id=None):
    def repo():
        return FakeRepo(repo_data, livefs=livefs, frozen=frozen, repo_id=repo_id)

    repo.pkgcore_config_type = ConfigHint(typename="repo")
    return basics.HardCodedConfigSection({"class": repo})


class FakeDomain:
    pkgcore_config_type = ConfigHint(
        types={"repos": "refs:repo", "binpkg": "refs:repo", "vdb": "refs:repo"},
        typename="domain",
    )

    def __init__(self, repos, binpkg, vdb):
        super().__init__()
        self.repos = repos
        self.source_repos_raw = util.RepositoryGroup(repos)
        self.installed_repos = util.RepositoryGroup(vdb)
        self.binary_repos_raw = util.RepositoryGroup(binpkg)
        self.vdb = vdb


def make_domain(repo=None, binpkg=None, vdb=None):
    if repo is None:
        repo = {}
    if binpkg is None:
        binpkg = {}
    if vdb is None:
        vdb = {}
    repos_config = make_repo_config(repo, repo_id="fake")
    binpkg_config = make_repo_config(binpkg, frozen=False, repo_id="fake_binpkg")
    vdb_config = make_repo_config(vdb, repo_id="fake_vdb")

    return basics.HardCodedConfigSection(
        {
            "class": FakeDomain,
            "repos": [repos_config],
            "binpkg": [binpkg_config],
            "vdb": [vdb_config],
            "default": True,
        }
    )


class FakeSyncer(base.Syncer):
    def __init__(self, *args, **kwargs):
        self.succeed = kwargs.pop("succeed", True)
        super().__init__(*args, **kwargs)
        self.synced = False

    def _sync(self, verbosity, **kwds):
        self.synced = True
        return self.succeed


class SyncableRepo(syncable.tree, util.SimpleTree):
    pkgcore_config_type = ConfigHint(typename="repo_config")

    def __init__(self, succeed=True):
        util.SimpleTree.__init__(self, {})
        syncer = FakeSyncer("/fake", "fake", succeed=succeed)
        syncable.tree.__init__(self, syncer)


success_section = basics.HardCodedConfigSection(
    {"class": SyncableRepo, "succeed": True}
)
failure_section = basics.HardCodedConfigSection(
    {"class": SyncableRepo, "succeed": False}
)


class TestSync(ArgParseMixin):
    _argparser = pmaint.sync

    def test_parser(self):
        values = self.parse(repo=success_section)
        assert ["repo"] == [x[0] for x in values.repos]
        values = self.parse("repo", repo=success_section)
        assert ["repo"] == [x[0] for x in values.repos]

    def test_sync(self):
        config = self.assertOut(
            [
                "*** syncing myrepo",
                "*** synced myrepo",
            ],
            myrepo=success_section,
        )
        assert config.objects.repo_config["myrepo"]._syncer.synced
        self.assertOut(
            [
                "*** syncing myrepo",
                "!!! failed syncing myrepo",
            ],
            myrepo=failure_section,
        )
        self.assertOutAndErr(
            [
                "*** syncing goodrepo",
                "*** synced goodrepo",
                "*** syncing badrepo",
                "!!! failed syncing badrepo",
                "",
                "*** sync results:",
                "*** synced: goodrepo",
                "!!! failed: badrepo",
            ],
            [],
            "goodrepo",
            "badrepo",
            goodrepo=success_section,
            badrepo=failure_section,
        )


class FakeSyncers(dict):
    """Hands out a syncer for any repo name asked for."""

    def __init__(self, succeed=True):
        super().__init__()
        self.succeed = succeed

    def __missing__(self, key):
        self[key] = syncer = FakeSyncer("/fake", "fake", succeed=self.succeed)
        return syncer


class FakeConfig:
    def __init__(self, syncers):
        self.objects = Options(syncer=syncers)


class TestImportRepos:
    @pytest.fixture
    def out(self):
        return PlainTextFormatter(BytesIO())

    @pytest.fixture
    def config_dir(self, tmp_path):
        """A config with gentoo configured, so new repos land beside it."""
        (conf := tmp_path / "repos.conf").mkdir()
        (conf / "gentoo.conf").write_text(
            "[gentoo]\n"
            f"location = {tmp_path / 'repos' / 'gentoo'}\n"
            "sync-uri = git://example.org/gentoo.git\n"
        )
        return tmp_path

    @pytest.fixture
    def syncers(self, monkeypatch):
        syncers = FakeSyncers()
        monkeypatch.setattr(pmaint, "load_config", lambda **kw: FakeConfig(syncers))
        return syncers

    @pytest.fixture(autouse=True)
    def remote_list(self, monkeypatch):
        monkeypatch.setattr(
            overlays,
            "remote_repos",
            lambda: (
                {
                    name: overlays.RemoteRepo(
                        name, "", (("git", f"https://example.org/{name}.git"),)
                    )
                    for name in ("guru", "midoverlay")
                }
                | {"cvs-only": overlays.RemoteRepo("cvs-only", "", ())}
            ),
        )

    @staticmethod
    def make_repo(path, masters):
        """Stand in for what a sync would have left on disk."""
        (path / "metadata").mkdir(parents=True)
        (path / "metadata" / "layout.conf").write_text(f"masters = {masters}\n")
        (path / "profiles").mkdir()
        return path

    def run(self, config_dir, out, *names, masters_of=None):
        options = Options(
            config_path=str(config_dir),
            import_repos=list(names),
            masters_of=masters_of,
            force=False,
            verbosity=0,
            debug=False,
        )
        return pmaint._import_repos(options, out, out)

    def test_new_repo_is_added(self, config_dir, out, syncers):
        assert self.run(config_dir, out, "guru") == (["guru"], [])
        assert (config_dir / "repos.conf" / "guru.conf").read_text() == (
            "[guru]\n"
            f"location = {config_dir / 'repos' / 'guru'}\n"
            "sync-type = git\n"
            "sync-uri = https://example.org/guru.git\n"
        )
        assert syncers["sync:guru"].synced

    def test_configured_repo_is_synced_rather_than_failed(
        self, config_dir, out, syncers
    ):
        assert self.run(config_dir, out, "gentoo") == (["gentoo"], [])
        # it was already there, so nothing new was written for it
        assert [x.name for x in (config_dir / "repos.conf").iterdir()] == [
            "gentoo.conf"
        ]
        assert syncers["sync:gentoo"].synced

    def test_unknown_repo_fails(self, config_dir, out, syncers):
        assert self.run(config_dir, out, "nonexistent") == ([], ["nonexistent"])

    def test_unsyncable_repo_fails(self, config_dir, out, syncers):
        assert self.run(config_dir, out, "cvs-only") == ([], ["cvs-only"])

    def test_failed_sync_is_reported(self, config_dir, out, monkeypatch):
        monkeypatch.setattr(
            pmaint, "load_config", lambda **kw: FakeConfig(FakeSyncers(succeed=False))
        )
        assert self.run(config_dir, out, "guru") == ([], ["guru"])

    def test_repeated_names_are_collapsed(self, config_dir, out, syncers):
        assert self.run(config_dir, out, "guru", "guru") == (["guru"], [])

    def test_not_a_config_dir(self, tmp_path, out):
        (path := tmp_path / "pkgcore.conf").touch()
        with pytest.raises(PkgcoreUserException, match="not a portage config dir"):
            self.run(path, out, "guru")

    def test_masters_of_a_standalone_repo(self, config_dir, out, syncers, tmp_path):
        leaf = self.make_repo(tmp_path / "leaf", "")
        assert self.run(config_dir, out, masters_of=str(leaf)) == ([], [])

    def test_masters_of_something_that_is_not_a_repo(self, config_dir, out, tmp_path):
        (path := tmp_path / "workspace").mkdir()
        with pytest.raises(PkgcoreUserException, match="not an ebuild repo"):
            self.run(config_dir, out, masters_of=str(path))

    def test_masters_are_imported(self, config_dir, out, syncers, tmp_path):
        leaf = self.make_repo(tmp_path / "leaf", "midoverlay")
        self.make_repo(config_dir / "repos" / "midoverlay", "")
        assert self.run(config_dir, out, masters_of=str(leaf)) == (["midoverlay"], [])
        assert (config_dir / "repos.conf" / "midoverlay.conf").exists()

    def test_masters_are_followed_transitively(
        self, config_dir, out, syncers, tmp_path
    ):
        leaf = self.make_repo(tmp_path / "leaf", "midoverlay")
        # what syncing midoverlay would have produced: it masters gentoo
        self.make_repo(config_dir / "repos" / "midoverlay", "gentoo")
        self.make_repo(config_dir / "repos" / "gentoo", "")
        synced, failed = self.run(config_dir, out, masters_of=str(leaf))
        assert synced == ["midoverlay", "gentoo"]
        assert failed == []

    def test_masters_of_a_failed_repo_are_not_followed(
        self, config_dir, out, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(
            pmaint, "load_config", lambda **kw: FakeConfig(FakeSyncers(succeed=False))
        )
        leaf = self.make_repo(tmp_path / "leaf", "midoverlay")
        self.make_repo(config_dir / "repos" / "midoverlay", "gentoo")
        assert self.run(config_dir, out, masters_of=str(leaf)) == ([], ["midoverlay"])


def derive_op(name, op, *a, **kw):
    if isinstance(name, str):
        name = [name]
    name = ["finalize_data"] + list(name)

    class new_op(op):
        def f(*a, **kw):
            return True

        for x in name:
            locals()[x] = f
        del f, x

    return new_op(*a, **kw)


class TestCopy(ArgParseMixin):
    _argparser = pmaint.copy

    def execute_main(self, *a, **kw):
        config = self.parse(*a, **kw)
        out = PlainTextFormatter(BytesIO())
        ret = config.main_func(config, out, out)
        return ret, config, out

    def test_normal_function(self):
        ret, config, _out = self.execute_main(
            "fake_binpkg",
            "--source-repo",
            "fake_vdb",
            "*",
            domain=make_domain(vdb={"sys-apps": {"portage": ["2.1", "2.3"]}}),
        )
        assert ret == 0, "expected non zero exit code"
        assert [pkg.cpvstr for pkg in config.target_repo.installed] == [
            "sys-apps/portage-2.1",
            "sys-apps/portage-2.3",
        ]
        assert config.target_repo.uninstalled == config.target_repo.replaced, (
            "uninstalled should be the same as replaced; empty"
        )

        d = {"sys-apps": {"portage": ["2.1", "2.2"]}}
        ret, config, _out = self.execute_main(
            "fake_binpkg",
            "--source-repo",
            "fake_vdb",
            "=sys-apps/portage-2.1",
            domain=make_domain(binpkg=d, vdb=d),
        )
        assert ret == 0, "expected non zero exit code"
        assert [[x.cpvstr for x in pkg] for pkg in config.target_repo.replaced] == [
            ["sys-apps/portage-2.1", "sys-apps/portage-2.1"]
        ]
        assert config.target_repo.uninstalled == config.target_repo.installed, (
            "installed should be the same as uninstalled; empty"
        )

    def test_ignore_existing(self):
        ret, config, _out = self.execute_main(
            "fake_binpkg",
            "--source-repo",
            "fake_vdb",
            "*",
            "--ignore-existing",
            domain=make_domain(vdb={"sys-apps": {"portage": ["2.1", "2.3"]}}),
        )
        assert ret == 0, "expected non zero exit code"
        assert [pkg.cpvstr for pkg in config.target_repo.installed] == [
            "sys-apps/portage-2.1",
            "sys-apps/portage-2.3",
        ]
        assert config.target_repo.uninstalled == config.target_repo.replaced, (
            "uninstalled should be the same as replaced; empty"
        )

        ret, config, _out = self.execute_main(
            "fake_binpkg",
            "--source-repo",
            "fake_vdb",
            "*",
            "--ignore-existing",
            domain=make_domain(
                binpkg={"sys-apps": {"portage": ["2.1"]}},
                vdb={"sys-apps": {"portage": ["2.1", "2.3"]}},
            ),
        )
        assert ret == 0, "expected non zero exit code"
        assert [pkg.cpvstr for pkg in config.target_repo.installed] == [
            "sys-apps/portage-2.3"
        ]
        assert config.target_repo.uninstalled == config.target_repo.replaced, (
            "uninstalled should be the same as replaced; empty"
        )


class TestRegen(ArgParseMixin):
    _argparser = pmaint.regen

    def test_parser(self):
        options = self.parse("fake", "--threads", "2", domain=make_domain())
        assert isinstance(options.repos[0], util.SimpleTree)
        assert options.threads == 2


class TestUpdateDescFiles:
    """Test the cache files written by ``pmaint regen``."""

    class FakeObserver:
        def __init__(self):
            self.errors = []

        def error(self, msg, *args, **kwds):
            self.errors.append(msg)

    class FakeRepo:
        def __init__(self, location):
            self.location = location
            self.packages = {}

    @pytest.mark.skipif(os.getuid() == 0, reason="need to be non root")
    @pytest.mark.parametrize(
        ("func", "dirname", "filename"),
        (
            (pmaint.update_use_local_desc, "profiles", "use.local.desc"),
            (pmaint.update_pkg_desc_index, "metadata", "pkg_desc_index"),
        ),
    )
    def test_unwritable_dir(self, tmp_path, func, dirname, filename):
        """The temporary file that actually failed is named in the error."""
        (target_dir := tmp_path / dirname).mkdir()
        target_dir.chmod(0o555)
        observer = self.FakeObserver()
        try:
            assert func(self.FakeRepo(str(tmp_path)), observer) == os.EX_IOERR
        finally:
            target_dir.chmod(0o755)

        assert len(observer.errors) == 1
        msg = observer.errors[0]
        assert f"Unable to update {filename} file {str(target_dir / filename)!r}" in msg
        # AtomicWriteFile resolves the target before deriving the temporary name
        temp_file = target_dir.resolve() / f".update.{filename}"
        assert f"Permission denied: {str(temp_file)!r}" in msg
