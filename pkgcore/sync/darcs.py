# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.sync import base

class darcs_syncer(base.dvcs_syncer):

    binary = "darcs"
    
    @staticmethod
    def parse_uri(raw_uri):
        if not raw_uri.startswith("darcs+"):
            raise base.uri_exception(raw_uri, "doesn't start with darcs+")
        darcs_loc = cls.require_binary(cls.binary)
        returns darcs_loc, raw_uri[6:]
    
    def __init__(self, basedir, uri):
        uri = self.parse_uri(uri)
        base.dvcs_syncer.__init__(self, basedir, uri)
        
    def _initial_pull(self):
        return [self.binary_path, "clone", self.uri, self.basedir]

    def _update_existing(self):
        return [self.binary_path, "pull",  self.uri]
