# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.sync import base

class cvs_syncer(base.dvcs_syncer):

    sets_env = True
    binary = "cvs"

    supported_uris = (
        ('cvs+', 5),
        ('cvs://', 5),
        )

    @classmethod
    def parse_uri(cls, raw_uri):
        if not raw_uri.startswith("cvs") and \
            not raw_uri.startswith("cvs+"):
            raise base.uri_exception(raw_uri, "must be cvs:// or cvs+${RSH}")
        if raw_uri.startswith("cvs://"):
            return None, raw_uri[len("cvs://"):]
        proto = raw_uri[len("cvs+"):].split(":", 1)
        if not proto[0]:
            raise base.uri_exception(raw_uri,
                "cvs+ requires the rsh alternative to be specified")
        if proto[0] == "anon":
            proto[0] = None
        elif proto[0] != "pserver":
            proto[0] = cls.require_binary(proto[0])
        return proto[0], proto[1].lstrip("/")

    def __init__(self, basedir, raw_uri):
        proto, uri = self.parse_uri(raw_uri)
        self.rsh = proto
        if self.rsh is None:
            uri = ":anoncvs:%s" % uri
        elif self.rsh == "pserver":
            uri = ":pserver:%s" % uri
            self.rsh = None
        else:
            uri = ":ext:%s" % uri
        host, self.module = uri.rsplit(":", 1)
        base.dvcs_syncer.__init__(self, basedir, host)

    @property
    def env(self):
        k = {"CVSROOT":self.uri}
        if self.rsh is not None:
            k["CVS_RSH"] = self.rsh
        return k

    def _update_existing(self):
        return [self.binary_path, "up"]

    def _initial_pull(self):
        return [self.binary_path, "co", "-d", self.basedir]
