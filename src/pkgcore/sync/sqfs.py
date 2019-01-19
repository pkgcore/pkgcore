__all__ = ("sqfs_syncer",)

from pkgcore.sync import base
from pkgcore.sync.http import http_syncer


class sqfs_syncer(http_syncer):

    supported_uris = (
        ('sqfs+http://', 5),
        ('sqfs+https://', 5),
    )

    @staticmethod
    def parse_uri(raw_uri):
        if raw_uri.startswith(("sqfs+http://", "sqfs+https://")):
            return raw_uri[5:]
        raise base.UriError(raw_uri, "unsupported URI")

    def __init__(self, basedir, uri, **kwargs):
        uri = self.parse_uri(uri)
        super().__init__(basedir, uri, **kwargs)

    def _sync(self, *args, **kwargs):
        ret = super()._sync(*args, **kwargs)
        # TODO: verify image checksum and gpg signature
        return ret
