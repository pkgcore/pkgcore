from unittest import mock

import pytest
from snakeoil.process import CommandNotFound

from pkgcore.sync import base, darcs


class TestDarcsSyncer:

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.repo_path = tmp_path / 'repo'

    def test_uri_parse(self):
        assert darcs.darcs_syncer.parse_uri("darcs+http://dar") == "http://dar"

        with pytest.raises(base.UriError):
            darcs.darcs_syncer.parse_uri("darcs://dar")

        # external binary doesn't exist
        with mock.patch('snakeoil.process.find_binary') as find_binary:
            find_binary.side_effect = CommandNotFound('darcs')
            with pytest.raises(base.SyncError):
                darcs.darcs_syncer(str(self.repo_path), "darcs+http://foon.com/dar")

        # fake that the external binary exists
        with mock.patch('snakeoil.process.find_binary') as find_binary:
            find_binary.return_value = 'bzr'
            o = darcs.darcs_syncer(str(self.repo_path), "darcs+http://dar")
            assert o.uri == "http://dar"
