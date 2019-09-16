import os
from unittest import mock

import pytest
from snakeoil.process import CommandNotFound

from pkgcore.sync import base, git


class TestGitSyncer:

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.repo_path = tmp_path / 'repo'

    def test_uri_parse(self):
        assert git.git_syncer.parse_uri("git+http://dar") == "http://dar"

        with pytest.raises(base.UriError):
            git.git_syncer.parse_uri("git+://dar")

        # external binary doesn't exist
        with mock.patch('snakeoil.process.find_binary') as find_binary:
            find_binary.side_effect = CommandNotFound('git')
            with pytest.raises(base.SyncError):
                git.git_syncer(str(self.repo_path), "git+http://foon.com/dar")

        # fake that the external binary exists
        with mock.patch('snakeoil.process.find_binary') as find_binary:
            find_binary.return_value = 'git'
            for proto in ('http', 'https'):
                for uri in (f"git+{proto}://repo.git", f"{proto}://repo.git"):
                    o = git.git_syncer(str(self.repo_path), uri)
                    assert o.uri == f"{proto}://repo.git"

    @mock.patch('snakeoil.process.spawn.spawn')
    def test_sync(self, spawn):
        uri = 'git://foo.git'
        with mock.patch('snakeoil.process.find_binary', return_value='git'):
            syncer = git.git_syncer(str(self.repo_path), uri)
        # initial sync
        syncer.sync()
        assert spawn.call_args[0] == (
            ['git', 'clone', uri, str(self.repo_path) + os.path.sep],)
        assert spawn.call_args[1]['cwd'] is None
        # repo update
        self.repo_path.mkdir()
        syncer.sync()
        assert spawn.call_args[0] == (['git', 'pull'],)
        assert spawn.call_args[1]['cwd'] == syncer.basedir


@pytest.mark_network
class TestGitSyncerReal:

    def test_sync(self, tmp_path):
        path = tmp_path / 'repo'
        syncer = git.git_syncer(str(path), "https://github.com/pkgcore/pkgrepo.git")
        assert syncer.sync()
        assert os.path.exists(os.path.join(path, 'metadata', 'layout.conf'))
        assert syncer.sync()
