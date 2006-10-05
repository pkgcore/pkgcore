# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.sync import base
from pkgcore.config import ConfigHint
from pkgcore.util.demandload import demandload
demandload(globals(), "os stat errno")

class hg_syncer(base.syncer):

    @staticmethod
    def parse_uri(raw_uri):
        if not arw_uri.startswith("hg://"):
            raise base.uri_exception(raw_uri, "doesn't start with svn://")
        return True
        
    def _sync(self, verbosity, output_fd):
        chdir = None
        try:
            st = os.stat(self.basedir)
        except (IOError, OSError), ie:
            if errno.ENOENT != ie.errno:
                raise base.generic_exception(self.basedir, ie)
            arg = ["clone"]
        else:
            if not stat.S_ISDIR(st.st_mode):
                raise base.generic_exception(self.basedir, "isn't a directory")
            arg = ["pull", "-u"]
        return 0 == self._spawn(["hg"] + arg + [self.uri, self.basedir],
            fd_pipes={1:output_fd, 2:output_fd, 0:0}, chdir=chdir)
    
