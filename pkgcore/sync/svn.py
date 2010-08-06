# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

__all__ = ("svn_syncer",)

from pkgcore.sync import base
from pkgcore.spawn import spawn_get_output
import os

class svn_syncer(base.ExternalSyncer):

    binary = "svn"

    supported_uris = (
        ('svn://', 5),
        ('svn+', 5),
        ('http+svn://',5),
        ('https+svn://',5)
        )

    @classmethod
    def is_usable_on_filepath(cls, path):
        svn_path = os.path.join(path, '.svn')
        if cls.disabled or not os.path.isdir(svn_path):
            return None
        code, data = spawn_get_output([cls.binary, "info", path])
        if code != 0:
            # should alert the user somehow
            return None
        for line in data:
            line = line.strip().split(":", 1)
            if len(line) != 2:
                continue
            if line[0] == 'URL':
                uri = "svn+%s" % (line[1].strip(),)
                return (cls._rewrite_uri_from_stat(svn_path, uri),)
        return None

    @staticmethod
    def parse_uri(raw_uri):
        if raw_uri.startswith("svn://"):
            return True
        elif raw_uri.startswith("http+svn://"):
            return True
        elif raw_uri.startswith("https+svn://"):
            return True
        elif raw_uri.startswith("svn+"):
            if raw_uri.startswith("svn+:"):
                raise base.uri_exception(raw_uri, "svn+:// isn't valid")
        else:
            raise base.uri_exception(raw_uri, "protocol unknown")
        return True

    def _sync(self, verbosity, output_fd):
        uri = self.uri
        if uri.startswith('svn+http://'):
            uri = uri.replace('svn+http://', 'http://')
        elif uri.startswith('svn+https://'):
            uri = uri.replace('svn+https://', 'https://')
        command = 'co'
        if not os.path.exists(self.basedir):
            return 0 == self._spawn([self.binary_path, "co",
                uri, self.basedir], {1:output_fd, 2:output_fd, 0:0})
        return 0 == self._spawn([self.binary_path, "update"],
            {1:output_fd, 2:output_fd, 0:0}, chdir=self.basedir)

