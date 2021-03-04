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
        self.repo_path = str(tmp_path / 'repo')

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
            base.Syncer(self.repo_path, f"foo_nonexistent_user::foon@site")

    @mock.patch('snakeoil.process.spawn.spawn')
    def test_usersync_disabled(self, spawn):
        o = base.Syncer(self.repo_path, f"http://foo/bar.git", usersync=False)
        o.uid == os_data.uid
        o.gid == os_data.gid

    @mock.patch('snakeoil.process.spawn.spawn')
    def test_usersync_portage_perms(self, spawn):
        # sync uses portage perms if repo dir doesn't exist
        o = base.Syncer(self.repo_path, f"http://foo/bar.git", usersync=True)
        o.uid == os_data.portage_uid
        o.gid == os_data.portage_gid

    @mock.patch('snakeoil.process.spawn.spawn')
    def test_usersync_repo_dir_perms(self, spawn):
        # and repo dir perms if it does exist
        with mock.patch('os.stat') as stat:
            stat.return_value = mock.Mock(st_uid=1234, st_gid=5678)
            o = base.Syncer(self.repo_path, f"http://foo/bar.git", usersync=True)
            stat.assert_called()
            assert o.uid == 1234
            assert o.gid == 5678


@mock.patch('snakeoil.process.find_binary')
class TestExternalSyncer:

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.repo_path = str(tmp_path / 'repo')

    def test_missing_binary(self, find_binary):
        find_binary.side_effect = CommandNotFound('foo')
        with pytest.raises(base.MissingBinary):
            base.ExternalSyncer(self.repo_path, 'http://dar')

    def test_existing_binary(self, find_binary):
        # fake external syncer
        class FooSyncer(base.ExternalSyncer):
            binary = 'foo'

        # fake that the external binary exists
        find_binary.side_effect = lambda x: x

        o = FooSyncer(self.repo_path, 'http://dar')
        assert o.uri == 'http://dar'
        assert o.binary == 'foo'

    @mock.patch('snakeoil.process.spawn.spawn')
    def test_usersync(self, spawn, find_binary):
        # fake external syncer
        class FooSyncer(base.ExternalSyncer):
            binary = 'foo'

        # fake that the external binary exists
        find_binary.side_effect = lambda x: x

        o = FooSyncer(self.repo_path, 'http://dar')
        o.uid = 1234
        o.gid = 2345
        o._spawn('cmd', pipes={})
        assert spawn.call_args[1]['uid'] == o.uid
        assert spawn.call_args[1]['gid'] == o.gid


@mock.patch('snakeoil.process.find_binary', return_value='git')
@mock.patch('snakeoil.process.spawn.spawn')
class TestVcsSyncer:

    def test_basedir_perms_error(self, spawn, find_binary, tmp_path):
        syncer = git.git_syncer(str(tmp_path), 'git://blah.git')
        with pytest.raises(base.PathError):
            with mock.patch('os.stat') as stat:
                stat.side_effect = EnvironmentError('fake exception')
                syncer.sync()

    def test_basedir_is_file_error(self, spawn, find_binary, tmp_path):
        repo = tmp_path / "repo"
        repo.touch()
        syncer = git.git_syncer(str(repo), 'git://blah.git')

        # basedir gets '/' appended by default and stat errors out
        with pytest.raises(base.PathError) as excinfo:
            syncer.sync()

        # remove trailing slash from basedir and file check catches it instead
        syncer.basedir = str(repo)
        with pytest.raises(base.PathError) as excinfo:
            syncer.sync()
        assert "isn't a directory" in str(excinfo.value)

    def test_verbose_sync(self, spawn, find_binary, tmp_path):
        syncer = git.git_syncer(str(tmp_path), 'git://blah.git')
        syncer.sync(verbosity=1)
        assert '-v' == spawn.call_args[0][0][-1]
        syncer.sync(verbosity=2)
        assert '-vv' == spawn.call_args[0][0][-1]

    def test_quiet_sync(self, spawn, find_binary, tmp_path):
        syncer = git.git_syncer(str(tmp_path), 'git://blah.git')
        syncer.sync(verbosity=-1)
        assert '-q' == spawn.call_args[0][0][-1]


class TestGenericSyncer:

    def test_init(self):
        with pytest.raises(base.UriError):
            base.GenericSyncer('/', 'seriouslynotaprotocol://blah/')

        syncer = base.GenericSyncer('/', f'tar+https://blah.tar.gz')
        assert tar.tar_syncer is syncer.__class__


class TestDisabledSyncer:

    def test_init(self):
        syncer = base.DisabledSyncer('/foo/bar', f'https://blah.git')
        assert syncer.disabled
        # syncing should also be disabled
        assert not syncer.uri
        assert not syncer.sync()


class TestAutodetectSyncer:

    def test_no_syncer_detected(self, tmp_path):
        syncer = base.AutodetectSyncer(str(tmp_path))
        assert isinstance(syncer, base.DisabledSyncer)

    @mock.patch('snakeoil.process.find_binary', return_value='git')
    def test_syncer_detected(self, find_binary, tmp_path):
        d = tmp_path / '.git'
        d.mkdir()
        syncer = base.AutodetectSyncer(str(tmp_path))
        assert isinstance(syncer, git.git_syncer)
