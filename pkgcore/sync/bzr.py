# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.sync import base
from pkgcore.config import ConfigHint
from pkgcore.util.demandload import demandload
demandload(globals(), "os stat errno")

class hg_syncer(base.syncer):

    @staticmethod
    def parse_uri(raw_uri):
        if not raw_uri.startswith("bzr+"):
            raise base.uri_exception(raw_uri, "doesn't start with bzr+")
        return uri[4:]

    def __init__(self, basedir, uri):
        uri = self.parse_uri
        base.syncer.__init__(self, basedir, uri)
        
    def _sync(self, verbosity, output_fd):
        chdir = None
        try:
            st = os.stat(self.basedir)
        except (IOError, OSError), ie:
            if errno.ENOENT != ie.errno:
                raise base.generic_exception(self.basedir, ie)
            arg = "get"
        else:
            if not stat.S_ISDIR(st.st_mode):
                raise base.generic_exception(self.basedir, "isn't a directory")
            arg = "pull"
        return 0 == self._spawn(["bzr", arg, self.uri, self.basedir],
            fd_pipes={1:output_fd, 2:output_fd, 0:0}, chdir=chdir)
    
