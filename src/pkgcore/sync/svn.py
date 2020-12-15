__all__ = ("svn_syncer",)

import os

from snakeoil.process.spawn import spawn_get_output

from . import base


class svn_syncer(base.ExternalSyncer):

    binary = "svn"

    supported_uris = (
        ('svn://', 5),
        ('svn+', 5),
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
                uri = f"svn+{line[1].strip()}"
                return (cls._rewrite_uri_from_stat(svn_path, uri),)
        return None

    @staticmethod
    def parse_uri(raw_uri):
        if raw_uri.startswith("svn://"):
            return raw_uri
        elif raw_uri.startswith("http+svn://"):
            return raw_uri[5:]
        elif raw_uri.startswith("https+svn://"):
            return raw_uri[6:]
        elif raw_uri.startswith("svn+"):
            if raw_uri.startswith("svn+:"):
                raise base.UriError(raw_uri, "svn+:// isn't valid")
            return raw_uri[4:]
        else:
            raise base.UriError(raw_uri, "protocol unknown")
        return raw_uri

    def _sync(self, verbosity, output_fd):
        uri = self.uri
        if uri.startswith('svn+http://'):
            uri = uri.replace('svn+http://', 'http://')
        elif uri.startswith('svn+https://'):
            uri = uri.replace('svn+https://', 'https://')
        if not os.path.exists(self.basedir):
            return 0 == self._spawn(
                [self.binary_path, "co", uri, self.basedir],
                {1: output_fd, 2: output_fd, 0: 0})
        return 0 == self._spawn(
            [self.binary_path, "update"],
            {1: output_fd, 2: output_fd, 0: 0}, cwd=self.basedir)
