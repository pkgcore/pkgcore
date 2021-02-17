__all__ = ("http_syncer",)

import errno
import os
import ssl
import sys
import urllib.request

from snakeoil.fileutils import AtomicWriteFile, readfile_ascii
from snakeoil.osutils import pjoin

from ..log import logger
from . import base


class http_syncer(base.Syncer):
    """Syncer that fetches files over HTTP(S)."""

    forcable = True

    def __init__(self, basedir, uri, dest=None, **kwargs):
        self.basename = os.path.basename(uri)
        super().__init__(basedir, uri, **kwargs)

    def _sync(self, verbosity, output_fd, force=False, **kwargs):
        dest = self._pre_download()

        if self.uri.lower().startswith('https://'):
            # default to using system ssl certs
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        else:
            context = None

        headers = {}
        etag_path = pjoin(self.basedir, '.etag')
        modified_path = pjoin(self.basedir, '.modified')

        if not force:
            # use cached ETag to check if updates exist
            previous_etag = readfile_ascii(etag_path, none_on_missing=True)
            if previous_etag:
                headers['If-None-Match'] = previous_etag

            # use cached modification timestamp to check if updates exist
            previous_modified = readfile_ascii(modified_path, none_on_missing=True)
            if previous_modified:
                headers['If-Modified-Since'] = previous_modified

        req = urllib.request.Request(self.uri, headers=headers, method='GET')

        # TODO: add customizable timeout
        try:
            resp = urllib.request.urlopen(req, context=context)
        except urllib.error.URLError as e:
            if e.getcode() == 304: # Not Modified
                logger.debug("content is unchanged")
                return True
            raise base.SyncError(f'failed fetching {self.uri!r}: {e.reason}') from e

        # Manually check cached values ourselves since some servers appear to
        # ignore If-None-Match or If-Modified-Since headers.
        convert = lambda x: x.strip() if x else None
        etag = resp.getheader('ETag')
        modified = resp.getheader('Last-Modified')
        if not force:
            if etag is not None and convert(etag) == convert(previous_etag):
                logger.debug(f"etag {etag} is equal, no update available")
                return True
            if modified is not None and convert(modified) == convert(previous_modified):
                logger.debug(f"header mtime is unmodified: {modified}")
                return True

        try:
            os.makedirs(self.basedir, exist_ok=True)
        except OSError as e:
            raise base.SyncError(
                f'failed creating repo dir {self.basedir!r}: {e.strerror}') from e

        length = resp.getheader('content-length')
        if length:
            length = int(length)
            blocksize = max(4096, length // 100)
        else:
            blocksize = 1000000

        try:
            self._download = AtomicWriteFile(dest, binary=True, perms=0o644)
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
            self._download.write(buf)
            size += len(buf)
            if length:
                sys.stdout.write('\r')
                progress = '=' * int(size / length * 50)
                percent = int(size / length * 100)
                sys.stdout.write("[%-50s] %d%%" % (progress, percent))
                sys.stdout.flush()

        self._post_download(dest)

        # TODO: store this in pkgcore cache dir instead?
        # update cached ETag/Last-Modified values
        if etag:
            with open(etag_path, 'w') as f:
                f.write(etag)
        if modified:
            with open(modified_path, 'w') as f:
                f.write(modified)

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
        # atomically create file
        self._download.close()
