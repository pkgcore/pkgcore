import os

import pytest

from pkgcore.sync import base
from pkgcore.sync.tar import tar_syncer


class TestTarSyncer:

    def test_uri_parse(self):
        assert tar_syncer.parse_uri("tar+http://repo.tar.gz") == "http://repo.tar.gz"

        # missing actual URI protocol
        with pytest.raises(base.UriError):
            tar_syncer.parse_uri("tar+://repo.tar.gz")

        # invalid compression suffix
        with pytest.raises(base.UriError):
            tar_syncer.parse_uri("tar+https://repo.tar.foo")

        for ext in tar_syncer.supported_exts:
            for proto in ('http', 'https'):
                for uri in (f"tar+{proto}://repo{ext}", f"{proto}://repo{ext}"):
                    o = tar_syncer("/tmp/foon", uri)
                    assert o.uri == f"{proto}://repo{ext}"


@pytest.mark_network
class TestTarSyncerReal:

    def test_sync(self, tmp_path):
        path = tmp_path / 'repo'
        syncer = tar_syncer(
            str(path), "https://github.com/pkgcore/pkgrepo/archive/master.tar.gz")
        assert syncer.sync()
        layout_conf = os.path.join(path, 'metadata', 'layout.conf')
        assert os.path.exists(layout_conf)
        stat = os.stat(layout_conf)
        # re-sync and verify that the repo didn't get replaced
        assert syncer.sync()
        assert stat == os.stat(layout_conf)
        # forcibly re-sync and verify that the repo gets replaced
        assert syncer.sync(force=True)
        assert stat != os.stat(layout_conf)
