import os
from unittest import mock

import pytest
from snakeoil.process import CommandNotFound

from pkgcore.sync import base, hg


class TestHgSyncer:

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.repo_path = tmp_path / 'repo'

    def test_uri_parse(self):
        assert hg.hg_syncer.parse_uri("hg+http://dar") == "http://dar"
        assert hg.hg_syncer.parse_uri("mercurial+http://dar") == "http://dar"

        with pytest.raises(base.UriError):
            hg.hg_syncer.parse_uri("hg://dar")

        # external binary doesn't exist
        with mock.patch('snakeoil.process.find_binary') as find_binary:
            find_binary.side_effect = CommandNotFound('svn')
            with pytest.raises(base.SyncError):
                hg.hg_syncer(str(self.repo_path), "hg+http://foon.com/dar")

        # fake that the external binary exists
        with mock.patch('snakeoil.process.find_binary') as find_binary:
            find_binary.return_value = 'hg'
            o = hg.hg_syncer(str(self.repo_path), "hg+http://dar")
            assert o.uri == "http://dar"

    @mock.patch('snakeoil.process.spawn.spawn')
    def test_sync(self, spawn):
        uri = 'https://foo/bar'
        with mock.patch('snakeoil.process.find_binary', return_value='hg'):
            syncer = hg.hg_syncer(str(self.repo_path), f'hg+{uri}')

        # initial sync
        syncer.sync()
        assert spawn.call_args[0] == (
            ['hg', 'clone', uri, str(self.repo_path) + os.path.sep],)
        assert spawn.call_args[1]['cwd'] is None
        # repo update
        self.repo_path.mkdir()
        syncer.sync()
        assert spawn.call_args[0] == (['hg', 'pull', '-u', uri],)
        assert spawn.call_args[1]['cwd'] == syncer.basedir
