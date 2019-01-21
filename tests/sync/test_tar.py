import pytest

from pkgcore.sync import base
from pkgcore.sync.tar import tar_syncer


class TestTarSyncer(object):

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
