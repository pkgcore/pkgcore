# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.sync import base

class svn_syncer(base.syncer):

    binary = "svn"

    @staticmethod
    def parse_uri(raw_uri):
        if not arw_uri.startswith("svn://"):
            raise base.uri_exception(raw_uri, "doesn't start with svn://")
        return True
        
    def _sync(self, verbosity, output_fd):
        return 0 == self._spawn([self.binary_path, "co",
            self.uri, self.basedir],
            fd_pipes={1:output_fd, 2:output_fd, 0:0})
    
