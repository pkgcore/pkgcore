import pytest

from pkgcore.sync import base
from pkgcore.sync.tar import tar_syncer


class TestGitSyncer(object):

    def test_uri_parse(self):
        assert tar_syncer.parse_uri("tar+http://repo.tar.gz") == "http://repo.tar.gz"

        # missing actual URI protocol
        with pytest.raises(base.UriError):
            tar_syncer.parse_uri("tar+://repo.tar.gz")

        # we don't yet support autodetection from URI suffixes
        with pytest.raises(base.UriError):
            tar_syncer.parse_uri("https://repo.tar.gz")

        # invalid compression suffix
        with pytest.raises(base.UriError):
            tar_syncer.parse_uri("tar+https://repo.tar.foo")

        o = tar_syncer("/tmp/foon", "tar+https://repo.tar.gz")
        assert o.uri == "https://repo.tar.gz"
