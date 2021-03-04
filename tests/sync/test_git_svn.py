# -*- coding: utf-8 -*-

from unittest import mock

import pytest
from snakeoil.process import CommandNotFound

from pkgcore.sync import base, git_svn


class TestGitSVNSyncer:

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.repo_path = tmp_path / 'repo'

    def test_uri_parse(self):
        assert git_svn.git_svn_syncer.parse_uri("git+svn+http://dar") == "http://dar"

        with pytest.raises(base.UriError):
            git_svn.git_svn_syncer.parse_uri("git+svn+://dar")

        # external binary doesn't exist
        with mock.patch('snakeoil.process.find_binary') as find_binary:
            find_binary.side_effect = CommandNotFound('git')
            with pytest.raises(base.SyncError):
                git_svn.git_svn_syncer(str(self.repo_path), "git+svn+http://foon.com/dar")

        # fake that the external binary exists
        with mock.patch('snakeoil.process.find_binary') as find_binary:
            find_binary.return_value = 'git'
            o = git_svn.git_svn_syncer(str(self.repo_path), "git+svn+http://dar")
            assert o.uri == "http://dar"
