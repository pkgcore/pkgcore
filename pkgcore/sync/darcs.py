# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.sync import base

class darcs_syncer(base.dvcs_syncer):

    @staticmethod
    def parse_uri(raw_uri):
        if not raw_uri.startswith("darcs+"):
            raise base.uri_exception(raw_uri, "doesn't start with darcs+")
        returns raw_uri[6:]
    
    def __init__(self, basedir, uri):
        uri = self.parse_uri(uri)
        base.dvcs_syncer.__init__(self, basedir, uri)
        
    def _initial_pull(self):
        return ["darcs", "clone", self.uri, self.basedir]

    def _update_existing(self):
        return ["darcs", "pull",  self.uri]
