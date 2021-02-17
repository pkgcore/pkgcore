__all__ = ("tar_syncer",)

import atexit
import os
import shutil
import subprocess
import tempfile
from functools import partial

from . import base
from .http import http_syncer


class tar_syncer(http_syncer, base.ExternalSyncer):

    binary = 'tar'

    supported_uris = (
        ('tar+http://', 5),
        ('tar+https://', 5),
    )

    # TODO: support more of the less used file extensions
    supported_protocols = ('http://', 'https://')
    supported_exts = ('.tar.gz', '.tar.bz2', '.tar.xz')

    @classmethod
    def parse_uri(cls, raw_uri):
        if raw_uri.startswith(("tar+http://", "tar+https://")):
            raw_uri = raw_uri[4:]
        if raw_uri.startswith(cls.supported_protocols) and raw_uri.endswith(cls.supported_exts):
            return raw_uri
        else:
            raise base.UriError(
                raw_uri, "unsupported compression format for tarball archive")
        raise base.UriError(raw_uri, "unsupported URI")

    def _pre_download(self):
        # create temp file for downloading
        self.tarball = tempfile.NamedTemporaryFile()
        # make sure temp file is deleted on exit
        atexit.register(partial(self.tarball.close))

        # determine names of tempdirs for staging
        basedir = self.basedir.rstrip(os.path.sep)
        repos_dir = os.path.dirname(basedir)
        repo_name = os.path.basename(basedir)
        self.tempdir = os.path.join(repos_dir, f'.{repo_name}.update')
        self.tempdir_old = os.path.join(repos_dir, f'.{repo_name}.old')
        # remove tempdirs on exit
        atexit.register(partial(shutil.rmtree, self.tempdir, ignore_errors=True))
        atexit.register(partial(shutil.rmtree, self.tempdir_old, ignore_errors=True))
        return self.tarball.name

    def _post_download(self, path):
        super()._post_download(path)

        # create tempdirs for staging
        try:
            os.makedirs(self.tempdir)
            os.makedirs(self.tempdir_old)
        except OSError as e:
            raise base.SyncError(f'failed creating repo update dirs: {e}')

        exts = {'gz': 'gzip', 'bz2': 'bzip2', 'xz': 'xz'}
        compression = exts[self.uri.rsplit('.', 1)[1]]
        # use tar instead of tarfile so we can easily strip leading path components
        # TODO: programmatically determine how many components to strip?
        cmd = [
            'tar', '--extract', f'--{compression}', '-f', self.tarball.name,
            '--strip-components=1', '--no-same-owner', '-C', self.tempdir
        ]

        try:
            subprocess.run(cmd, stderr=subprocess.PIPE, check=True, encoding='utf8')
        except subprocess.CalledProcessError as e:
            error = e.stderr.splitlines()[0]
            raise base.SyncError(f'failed to unpack tarball: {error}')

        # TODO: verify gpg data if it exists

        try:
            if os.path.exists(self.basedir):
                # move old repo out of the way if it exists
                os.rename(self.basedir, self.tempdir_old)
            # move new, unpacked repo into place
            os.rename(self.tempdir, self.basedir)
        except OSError as e:
            raise base.SyncError(f'failed to update repo: {e.strerror}') from e
