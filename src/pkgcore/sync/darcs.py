__all__ = ("darcs_syncer",)

from . import base


class darcs_syncer(base.VcsSyncer):

    binary = "darcs"

    supported_uris = (
        ('darcs+', 5),
    )

    @staticmethod
    def parse_uri(raw_uri):
        if not raw_uri.startswith("darcs+"):
            raise base.UriError(raw_uri, "doesn't start with darcs+")
        return raw_uri[6:]

    def _initial_pull(self):
        return [self.binary_path, "clone", self.uri, self.basedir]

    def _update_existing(self):
        return [self.binary_path, "pull", self.uri]
