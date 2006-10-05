# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.sync import base

class hg_syncer(base.dvcs_syncer):

    @staticmethod
    def parse_uri(raw_uri):
        if not raw_uri.startswith("hg://"):
            raise base.uri_exception(raw_uri, "doesn't start with hg://")
        return True
        
    def _initial_pull(self):
        return ["hg", "clone", self.uri, self.basedir]

    def _update_existing(self):
        return ["hg", "pull", "-u", self.uri]
