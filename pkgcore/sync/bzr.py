# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.sync import base

class bzr_syncer(base.dvcs_syncer):

    @staticmethod
    def parse_uri(raw_uri):
        if not raw_uri.startswith("bzr+"):
            raise base.uri_exception(raw_uri, "doesn't start with bzr+")
        return uri[4:]

    def __init__(self, basedir, uri):
        uri = self.parse_uri(uri)
        base.dvcs_syncer.__init__(self, basedir, uri)
        
    def _initial_pull(self):
        return ["bzr", "get", self.basedir, self.uri]
    
    def _update_existing(self):
        return ["bzr", "merge", self.uri]
