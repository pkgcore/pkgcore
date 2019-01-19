__all__ = ("http_syncer",)

import errno
import os
import ssl
import sys
import urllib.request

from snakeoil.fileutils import AtomicWriteFile
from snakeoil.osutils import pjoin

from pkgcore.sync import base


class http_syncer(base.Syncer):

    supported_uris = (
        ('http://', 5),
        ('https://', 5),
    )

    def __init__(self, basedir, uri, **kwargs):
        self.basename = os.path.basename(uri)
        self.dest = pjoin(basedir, self.basename)
        super().__init__(basedir, uri, **kwargs)

    def _sync(self, verbosity, output_fd, **kwds):
        # default to using system ssl certs
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        try:
            resp = urllib.request.urlopen(self.uri, context=context)
        except urllib.error.URLError as e:
            raise base.ConnectionError(str(e.reason)) from e

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
            f = AtomicWriteFile(self.dest, binary=True, perms=0o644)
        except OSError as e:
            raise base.PathError(self.basedir, e.strerror) from e

        # retrieve the file while providing simple progress output
        size = 0
        while True:
            buf = resp.read(blocksize)
            if not buf:
                sys.stdout.write('\n')
                break
            f.write(buf)
            size += len(buf)
            if length:
                sys.stdout.write('\r')
                progress = '=' * int(size / length * 50)
                percent = int(size / length * 100)
                sys.stdout.write("[%-50s] %d%%" % (progress, percent))

        # atomically create file
        f.close()

        # update timestamp
        with open(timestamp, 'w') as f:
            f.write(last_modified)

        return True
