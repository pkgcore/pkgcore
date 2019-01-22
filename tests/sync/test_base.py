# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import os
import pwd
from unittest import mock

import pytest

from pkgcore import os_data
from pkgcore.sync import base, git, tar
from tests.sync.syncer import make_bogus_syncer, make_valid_syncer

valid = make_valid_syncer(base.ExternalSyncer)
bogus = make_bogus_syncer(base.ExternalSyncer)

existing_user = pwd.getpwall()[0].pw_name
existing_uid = pwd.getpwnam(existing_user).pw_uid


class TestSyncer(object):

    def test_split_users(self):
        o = base.Syncer("/tmp/foon", "http://dar")
        assert o.uid == os.getuid()
        assert o.uri == "http://dar"

        o = base.Syncer("/tmp/foon", f"http://{existing_user}::@site")
        assert o.uid == existing_uid
        assert o.uri == "http://site"

        o = base.Syncer("/tmp/foon", f"http://{existing_user}::foon@site")
        assert o.uid == existing_uid
        assert o.uri == "http://foon@site"

        o = base.Syncer("/tmp/foon", f"{existing_user}::foon@site")
        assert o.uid == existing_uid
        assert o.uri == "foon@site"

    def test_usersync_disabled(self):
        o = base.Syncer("/tmp/foon", f"http://foo/bar.git", usersync=False)
        o.uid == os_data.uid
        o.gid == os_data.gid

    def test_usersync_enabled(self, tmp_path):
        # sync uses portage perms if repo dir doesn't exist
        o = base.Syncer("/tmp/foo/nonexistent/path", f"http://foo/bar.git", usersync=True)
        o.uid == os_data.portage_uid
        o.gid == os_data.portage_gid

        # and repo dir perms if it does exist
        with mock.patch('os.stat') as stat:
            stat.return_value = mock.Mock(st_uid=1234, st_gid=5678)
            o = base.Syncer(str(tmp_path), f"http://foo/bar.git", usersync=True)
            stat.assert_called()
            assert o.uid == 1234
            assert o.gid == 5678


class TestExternalSyncer(object):

    def test_missing_binary(self):
        with pytest.raises(base.MissingBinary):
            bogus("/tmp/foon", "http://dar")

    def test_existing_binary(self):
        o = valid("/tmp/foon", "http://dar")
        assert o.uri == "http://dar"
        assert o.binary == "/bin/sh"


@mock.patch('snakeoil.process.find_binary')
@mock.patch('snakeoil.process.spawn.spawn')
class TestVcsSyncer(object):

    def test_basedir_perms_error(self, spawn, find_binary, tmp_path):
        find_binary.return_value = 'git'
        syncer = git.git_syncer(str(tmp_path), 'git://blah.git')
        with pytest.raises(base.PathError):
            with mock.patch('os.stat') as stat:
                stat.side_effect = EnvironmentError('fake exception')
                syncer.sync()

    def test_basedir_is_file_error(self, spawn, find_binary, tmp_path):
        find_binary.return_value = 'git'
        repo = tmp_path / "repo"
        repo.touch()
        syncer = git.git_syncer(str(repo), 'git://blah.git')
        with pytest.raises(base.PathError):
            syncer.sync()

    def test_verbose_sync(self, spawn, find_binary, tmp_path):
        find_binary.return_value = 'git'
        syncer = git.git_syncer(str(tmp_path), 'git://blah.git')
        syncer.sync(verbosity=1)
        assert '-v' == spawn.call_args[0][0][-1]
        syncer.sync(verbosity=2)
        assert '-vv' == spawn.call_args[0][0][-1]

    def test_quiet_sync(self, spawn, find_binary, tmp_path):
        find_binary.return_value = 'git'
        syncer = git.git_syncer(str(tmp_path), 'git://blah.git')
        syncer.sync(verbosity=-1)
        assert '-q' == spawn.call_args[0][0][-1]


class TestGenericSyncer(object):

    def test_init(self):
        with pytest.raises(base.UriError):
            base.GenericSyncer('/', 'seriouslynotaprotocol://blah/')

        syncer = base.GenericSyncer('/', f'tar+https://blah.tar.gz')
        assert tar.tar_syncer is syncer.__class__


class TestDisabledSyncer(object):

    def test_init(self):
        syncer = base.DisabledSyncer('/foo/bar', f'https://blah.git')
        assert syncer.disabled
        # syncing should also be disabled
        assert not syncer.uri
        assert not syncer.sync()


class TestAutodetectSyncer(object):

    def test_no_syncer_detected(self, tmp_path):
        syncer = base.AutodetectSyncer(str(tmp_path))
        assert isinstance(syncer, base.DisabledSyncer)

    def test_syncer_detected(self, tmp_path):
        d = tmp_path / ".git"
        d.mkdir()
        syncer = base.AutodetectSyncer(str(tmp_path))
        assert isinstance(syncer, git.git_syncer)
