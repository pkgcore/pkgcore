import os
import pwd
from unittest import mock

import pytest
from snakeoil.process import CommandNotFound

from pkgcore import os_data
from pkgcore.sync import base, git, tar

existing_user = pwd.getpwall()[0].pw_name
existing_uid = pwd.getpwnam(existing_user).pw_uid


class TestSyncer:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.repo_path = str(tmp_path / "repo")

    def test_split_users(self):
        o = base.Syncer(self.repo_path, "http://dar")
        assert o.uid == os.getuid()
        assert o.uri == "http://dar"

        o = base.Syncer(self.repo_path, f"http://{existing_user}::@site")
        assert o.uid == existing_uid
        assert o.uri == "http://site"

        o = base.Syncer(self.repo_path, f"http://{existing_user}::foon@site")
        assert o.uid == existing_uid
        assert o.uri == "http://foon@site"

        o = base.Syncer(self.repo_path, f"{existing_user}::foon@site")
        assert o.uid == existing_uid
        assert o.uri == "foon@site"

        with pytest.raises(base.MissingLocalUser):
            base.Syncer(self.repo_path, "foo_nonexistent_user::foon@site")

    @mock.patch("pkgcore.sync.base.subprocess.run")
    def test_usersync_disabled(self, run):
        o = base.Syncer(self.repo_path, "http://foo/bar.git", usersync=False)
        assert o.uid == os_data.uid
        assert o.gid == os_data.gid

    @mock.patch("pkgcore.sync.base.subprocess.run")
    def test_usersync_portage_perms(self, run):
        # sync uses portage perms if repo dir doesn't exist
        o = base.Syncer(self.repo_path, "http://foo/bar.git", usersync=True)
        assert o.uid == os_data.portage_uid
        assert o.gid == os_data.portage_gid

    @mock.patch("pkgcore.sync.base.subprocess.run")
    def test_usersync_repo_dir_perms(self, run):
        # and repo dir perms if it does exist
        with mock.patch("os.stat") as stat:
            stat.return_value = mock.Mock(st_uid=1234, st_gid=5678)
            o = base.Syncer(self.repo_path, "http://foo/bar.git", usersync=True)
            stat.assert_called()
            assert o.uid == 1234
            assert o.gid == 5678


@mock.patch("snakeoil.process.find_binary")
class TestExternalSyncer:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.repo_path = str(tmp_path / "repo")

    def test_missing_binary(self, find_binary):
        find_binary.side_effect = CommandNotFound("foo")
        with pytest.raises(base.MissingBinary):
            base.ExternalSyncer(self.repo_path, "http://dar")

    def test_existing_binary(self, find_binary):
        # fake external syncer
        class FooSyncer(base.ExternalSyncer):
            binary = "foo"

        # fake that the external binary exists
        find_binary.side_effect = lambda x: x

        o = FooSyncer(self.repo_path, "http://dar")
        assert o.uri == "http://dar"
        assert o.binary == "foo"

    @mock.patch("pkgcore.sync.base.subprocess.run")
    def test_usersync(self, run, find_binary):
        # fake external syncer
        class FooSyncer(base.ExternalSyncer):
            binary = "foo"

        # fake that the external binary exists
        find_binary.side_effect = lambda x: x

        o = FooSyncer(self.repo_path, "http://dar")
        o.uid = 1234
        o.gid = 2345
        o._spawn("cmd")
        assert run.call_args[1]["user"] == o.uid
        assert run.call_args[1]["group"] == o.gid


@mock.patch("snakeoil.process.find_binary", return_value="git")
@mock.patch("pkgcore.sync.base.subprocess.run")
class TestVcsSyncer:
    def test_basedir_perms_error(self, run, find_binary, tmp_path):
        syncer = git.git_syncer(str(tmp_path), "git://blah.git")
        with pytest.raises(base.PathError), mock.patch("os.stat") as stat:
            stat.side_effect = OSError("fake exception")
            syncer.sync()

    def test_basedir_is_file_error(self, run, find_binary, tmp_path):
        repo = tmp_path / "repo"
        repo.touch()
        syncer = git.git_syncer(str(repo), "git://blah.git")

        # basedir gets '/' appended by default and stat errors out
        with pytest.raises(base.PathError) as excinfo:
            syncer.sync()

        # remove trailing slash from basedir and file check catches it instead
        syncer.basedir = str(repo)
        with pytest.raises(base.PathError) as excinfo:
            syncer.sync()
        assert "isn't a directory" in str(excinfo.value)

    def test_verbose_sync(self, run, find_binary, tmp_path):
        syncer = git.git_syncer(str(tmp_path), "git://blah.git")
        syncer.sync(verbosity=1)
        assert "-v" == run.call_args[0][0][-1]
        syncer.sync(verbosity=2)
        assert "-vv" == run.call_args[0][0][-1]

    def test_quiet_sync(self, run, find_binary, tmp_path):
        syncer = git.git_syncer(str(tmp_path), "git://blah.git")
        syncer.sync(verbosity=-1)
        assert "-q" == run.call_args[0][0][-1]


class TestGenericSyncer:
    def test_init(self):
        with pytest.raises(base.UriError):
            base.GenericSyncer("/", "seriouslynotaprotocol://blah/")

        syncer = base.GenericSyncer("/", "tar+https://blah.tar.gz")
        assert tar.tar_syncer is syncer.__class__


class TestDisabledSyncer:
    def test_init(self):
        syncer = base.DisabledSyncer("/foo/bar", "https://blah.git")
        assert syncer.disabled
        # syncing should also be disabled
        assert not syncer.uri
        assert not syncer.sync()


class TestAutodetectSyncer:
    def test_no_syncer_detected(self, tmp_path):
        syncer = base.AutodetectSyncer(str(tmp_path))
        assert isinstance(syncer, base.DisabledSyncer)

    @mock.patch("snakeoil.process.find_binary", return_value="git")
    def test_syncer_detected(self, find_binary, tmp_path):
        d = tmp_path / ".git"
        d.mkdir()
        syncer = base.AutodetectSyncer(str(tmp_path))
        assert isinstance(syncer, git.git_syncer)
