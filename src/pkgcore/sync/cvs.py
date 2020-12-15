__all__ = ("cvs_syncer",)

import os

from . import base


class cvs_syncer(base.VcsSyncer):

    binary = "cvs"

    supported_uris = (
        ('cvs+', 5),
        ('cvs://', 5),
    )

    @classmethod
    def is_usable_on_filepath(cls, path):
        cvs_path = os.path.join(path, "CVS")
        if cls.disabled or not os.path.isdir(cvs_path):
            return None
        return (cls._rewrite_uri_from_stat(cvs_path, 'cvs://'),)

    @classmethod
    def _parse_uri(cls, raw_uri):
        if not raw_uri.startswith("cvs") and \
                not raw_uri.startswith("cvs+"):
            raise base.UriError(raw_uri, "must be cvs:// or cvs+${RSH}")
        if raw_uri.startswith("cvs://"):
            return None, raw_uri[len("cvs://"):]
        proto = raw_uri[len("cvs+"):].split(":", 1)
        if not proto[0]:
            raise base.UriError(
                raw_uri, "cvs+ requires the rsh alternative to be specified")
        if proto[0] == "anon":
            proto[0] = None
        elif proto[0] != "pserver":
            try:
                proto[0] = cls.require_binary(proto[0])
            except base.MissingBinary:
                raise base.UriError(
                    raw_uri, f"missing rsh binary: {proto[0]!r}")
        return proto[0], proto[1].lstrip("/")

    def __init__(self, basedir, raw_uri, **kwargs):
        proto, uri = self._parse_uri(raw_uri)
        self.rsh = proto
        if self.rsh is None:
            uri = f":anoncvs:{uri}"
        elif self.rsh == "pserver":
            uri = f":pserver:{uri}"
            self.rsh = None
        else:
            uri = f":ext:{uri}"
        host, self.module = uri.rsplit(":", 1)
        super().__init__(basedir, host, **kwargs)

        self.env['CVSROOT'] = self.uri
        if self.rsh is not None:
            self.env['CVS_RSH'] = self.rsh

    def _update_existing(self):
        return [self.binary_path, "up"]

    def _initial_pull(self):
        return [self.binary_path, "co", "-d", self.basedir]
