# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.sync import base

class bzr_syncer(base.dvcs_syncer):

    binary = "bzr"

    supported_uris = (
        ('bzr+', 5),
        )

    @staticmethod
    def parse_uri(raw_uri):
        if not raw_uri.startswith("bzr+"):
            raise base.uri_exception(raw_uri, "doesn't start with bzr+")
        return raw_uri[4:]

    def __init__(self, basedir, uri, **kwargs):
        uri = self.parse_uri(uri)
        base.dvcs_syncer.__init__(self, basedir, uri, **kwargs)

    def _initial_pull(self):
        return [self.binary_path, "get", self.basedir, self.uri]

    def _update_existing(self):
        return [self.binary_path, "pull", self.uri]
