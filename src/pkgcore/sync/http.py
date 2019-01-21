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
    """Syncer that fetches files over HTTP(S)."""

    def __init__(self, basedir, uri, dest=None, **kwargs):
        self.basename = os.path.basename(uri)
        super().__init__(basedir, uri, **kwargs)

    def _sync(self, verbosity, output_fd, **kwds):
        dest = self._pre_download()

        if self.uri.startswith('https://'):
            # default to using system ssl certs
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        else:
            context = None

        # TODO: add customizable timeout
        try:
            resp = urllib.request.urlopen(self.uri, context=context)
        except urllib.error.URLError as e:
            raise base.SyncError(f'failed fetching {self.uri!r}: {e.reason}') from e

        try:
            os.makedirs(self.basedir, exist_ok=True)
        except OSError as e:
            raise base.SyncError(
                f'failed creating repo dir {self.basedir!r}: {e.strerror}') from e

        # check if updates exist
        modified = pjoin(self.basedir, '.modified')
        etag = resp.getheader('ETag')
        if etag and os.path.exists(modified):
            etag = etag.strip('\'"')
            with open(modified, 'r') as f:
                previous = f.read()
                if etag == previous:
                    return True

        length = resp.getheader('content-length')
        if length:
            length = int(length)
            blocksize = max(4096, length//100)
        else:
            blocksize = 1000000

        try:
            f = AtomicWriteFile(dest, binary=True, perms=0o644)
        except OSError as e:
            raise base.PathError(self.basedir, e.strerror) from e

        # retrieve the file while providing simple progress output
        size = 0
        while True:
            buf = resp.read(blocksize)
            if not buf:
                if length:
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

        self._post_download(dest)

        # TODO: store this in pkgcore cache dir instead?
        # update timestamp
        if etag:
            with open(modified, 'w') as f:
                f.write(etag)

        return True

    def _pre_download(self):
        """Pre-download initialization.

        Returns file path to download file to.
        """
        return pjoin(self.basedir, self.basename)

    def _post_download(self, path):
        """Post-download file processing.

        Args:
            path (str): path to downloaded file
        """
