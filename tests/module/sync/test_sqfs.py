import os

import pytest

from pkgcore.sync import base
from pkgcore.sync.sqfs import sqfs_syncer


class TestSqfsSyncer:

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


@pytest.mark_network
class TestSqfsSyncerReal:

    def test_sync(self, tmp_path):
        path = tmp_path / 'repo'
        syncer = sqfs_syncer(
                str(path),
                "sqfs+http://distfiles.gentoo.org/snapshots/squashfs/gentoo-current.lzo.sqfs")
        assert syncer.sync()
        sqfs = os.path.join(syncer.basedir, syncer.basename)
        assert os.path.exists(sqfs)
        stat = os.stat(sqfs)
        # re-sync and verify that the repo didn't get replaced
        assert syncer.sync()
        assert stat == os.stat(sqfs)
        # forcibly re-sync and verify that the repo gets replaced
        assert syncer.sync(force=True)
        assert stat != os.stat(sqfs)
