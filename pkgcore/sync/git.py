# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.sync import base

class git_syncer(base.dvcs_syncer):

    binary = "git"

    supported_uris = (
        ('git://', 5),
        ('git+', 5),
        )

    @staticmethod
    def parse_uri(raw_uri):
        if not raw_uri.startswith("git+") and not raw_uri.startswith("git://"):
            raise base.uri_exception(raw_uri,
                "doesn't start with git+ nor git://")
        if raw_uri.startswith("git+"):
            if raw_uri.startswith("git+:"):
                raise base.uri_exception(raw_uri,
                    "need to specify the sub protocol if using git+")
            return raw_uri[4:]
        return raw_uri

    def __init__(self, basedir, uri, **kwargs):
        uri = self.parse_uri(uri)
        base.dvcs_syncer.__init__(self, basedir, uri, **kwargs)

    def _initial_pull(self):
        return [self.binary_path, "clone", self.uri, self.basedir]

    def _update_existing(self):
        return [self.binary_path, "pull"]
