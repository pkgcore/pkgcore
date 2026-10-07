from unittest import mock

import pytest

from pkgcore.sync import base, bzr


class TestBzrSyncer:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.repo_path = tmp_path / "repo"

    def test_uri_parse(self):
        assert bzr.bzr_syncer.parse_uri("bzr+http://dar") == "http://dar"

        with pytest.raises(base.UriError):
            bzr.bzr_syncer.parse_uri("bzr://dar")

        # external binary doesn't exist
        with mock.patch("shutil.which") as which:
            which.return_value = None
            with pytest.raises(base.SyncError):
                bzr.bzr_syncer(str(self.repo_path), "bzr+http://foon.com/dar")

        # fake that the external binary exists
        with mock.patch("shutil.which") as which:
            which.return_value = "bzr"
            o = bzr.bzr_syncer(str(self.repo_path), "bzr+http://dar")
            assert o.uri == "http://dar"
