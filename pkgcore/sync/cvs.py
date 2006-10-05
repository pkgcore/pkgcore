# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.sync import base
from pkgcore.config import ConfigHint
from pkgcore.util.demandload import demandload
demandload(globals(), "os stat errno")

class cvs_syncer(base.dvcs_syncer):

    sets_env = True
    
    @staticmethod
    def parse_uri(raw_uri):
        proto = raw_uri.split(":", 1)[0]
        if not proto in ("cvs", "cvs+ssh"):
            raise base.uri_exception(raw_uri, "must be cvs:// or cvs+ssh://")
        return proto, raw_uri.lstrip("/")

    def __init__(self, basedir, uri):
        proto, raw_uri = self.parse_uri(uri)
        if proto == 'cvs':
            self.rsh = None
        else:
            self.rsh = proto.split("+", 1)[-1]
        host, self.module = uri.rsplit(":" ,1)
        nase.dvcs_syncer.__init__(self, basedir, host)
        
    @property
    def env(self):
        k = {"CVSROOT":self.uri}
        if self.rsh is not None:
            k["CVS_RSH"] = self.rsh
        return k

    def _update_existing(self):
        return ["cvs", "up"]

    def _initial_pull(self):
        return ["cvs", "co", "-d", self.basedir]
