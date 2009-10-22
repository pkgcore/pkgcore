# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.sync import base
from pkgcore.spawn import spawn_get_output
import os

class bzr_syncer(base.dvcs_syncer):

    binary = "bzr"

    supported_uris = (
        ('bzr+', 5),
        )

    @classmethod
    def is_usable_on_filepath(cls, path):
        bzr_path = os.path.join(path, '.bzr')
        if cls.disabled or not os.path.isdir(bzr_path):
            return None
        code, data = spawn_get_output([cls.binary, "info", path])
        if code != 0:
            # should alert the user somehow
            return None
        for line in data:
            line = line.strip().split(":", 1)
            if len(line) != 2:
                continue
            if line[0] == 'parent branch':
                uri = "bzr+%s" % (line[1].strip(),)
                return (cls._rewrite_uri_from_stat(bzr_path, uri),)
        return None

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
