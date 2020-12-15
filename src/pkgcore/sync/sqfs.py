__all__ = ("sqfs_syncer",)

from . import base
from .http import http_syncer


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

    def _post_download(self, path):
        # TODO: verify gpg data if it exists
        super()._post_download(path)
