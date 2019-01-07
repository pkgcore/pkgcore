__all__ = ("file_syncer",)

import errno
import os
import sys
import tempfile
import urllib.request

from snakeoil.osutils import pjoin

from pkgcore.sync import base


class file_syncer(base.Syncer):

    supported_uris = (
        ('file+http://', 5),
        ('file+https://', 5),
    )

    @staticmethod
    def parse_uri(raw_uri):
        if raw_uri.startswith(("file+http://", "file+https://")):
            return raw_uri[5:]
        raise base.UriError(raw_uri, "unsupported URI")

    def __init__(self, basedir, uri, **kwargs):
        uri = self.parse_uri(uri)
        self.basename = os.path.basename(uri)
        self.dest = pjoin(basedir, self.basename)
        super().__init__(basedir, uri, **kwargs)

    def _sync(self, verbosity, output_fd, **kwds):
        resp = urllib.request.urlopen(self.uri)

        # TODO: cache/use ETag from header if it exists and fallback to last-modified
        # to check if updates exist
        timestamp = pjoin(self.basedir, '.timestamp')
        last_modified = resp.getheader('last-modified')
        if os.path.exists(self.dest) and os.path.exists(timestamp):
            with open(timestamp, 'r') as f:
                previous = f.read()
                if last_modified == previous:
                    return True

        length = resp.getheader('content-length')
        if length:
            length = int(length)
            blocksize = max(4096, length//100)
        else:
            blocksize = 1000000

        try:
            tmpfile = tempfile.NamedTemporaryFile(
                prefix=f'.{self.basename}-', dir=self.basedir, delete=False)

            size = 0
            while True:
                buf = resp.read(blocksize)
                if not buf:
                    sys.stdout.write('\n')
                    break
                tmpfile.write(buf)
                size += len(buf)
                if length:
                    sys.stdout.write('\r')
                    progress = '=' * int(size / length * 50)
                    percent = int(size / length * 100)
                    sys.stdout.write("[%-50s] %d%%" % (progress, percent))

            os.rename(tmpfile.name, self.dest)
            with open(timestamp, 'w') as f:
                f.write(last_modified)
        except OSError as e:
            raise base.PathError(self.basedir, e.strerror) from e

        return True
