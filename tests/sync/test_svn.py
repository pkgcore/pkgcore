from unittest import mock

import pytest
from snakeoil.process import CommandNotFound

from pkgcore.sync import base, svn


class TestSVNSyncer:

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.repo_path = tmp_path / 'repo'

    def test_uri_parse(self):
        with pytest.raises(base.UriError):
            svn.svn_syncer.parse_uri("svn+://dar")

        # external binary doesn't exist
        with mock.patch('snakeoil.process.find_binary') as find_binary:
            find_binary.side_effect = CommandNotFound('svn')
            with pytest.raises(base.SyncError):
                svn.svn_syncer(str(self.repo_path), "svn+http://foon.com/dar")

        # fake that the external binary exists
        with mock.patch('snakeoil.process.find_binary') as find_binary:
            find_binary.return_value = 'svn'
            o = svn.svn_syncer(str(self.repo_path), "svn+http://dar")
            assert o.uri == "http://dar"
