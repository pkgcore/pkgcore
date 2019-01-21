import pytest

from pkgcore.sync import base
from pkgcore.sync.sqfs import sqfs_syncer


class TestSqfsSyncer(object):

    def test_uri_parse(self):
        assert sqfs_syncer.parse_uri("sqfs+http://repo.lzo.sqfs") == "http://repo.lzo.sqfs"

        # missing actual URI protocol
        with pytest.raises(base.UriError):
            sqfs_syncer.parse_uri("sqfs+://repo.lzo.sqfs")

        # we don't yet support autodetection from URI suffixes
        with pytest.raises(base.UriError):
            sqfs_syncer.parse_uri("https://repo.lzo.sqfs")

        o = sqfs_syncer("/tmp/foon", "sqfs+https://repo.lzo.sqfs")
        assert o.uri == "https://repo.lzo.sqfs"
