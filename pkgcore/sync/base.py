# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.demandload import demandload
demandload(globals(), "pkgcore:spawn")

class syncer(object):

    forcable=False
    
    def __init__(self, local_path, uri, default_verbosity=0):
        self.verbose = default_verbosity
        self.basedir = local_path
        self.uri = uri
    
    def sync(self, verbosity=None, force=False):
        kwds = {}
        if self.forcable and force:
            kwds["force"] = True
        if verbosity is None:
            verbosity = self.verbose
        # output_fd is harded coded as stdout atm.
        return self._sync(verbosity, 1, **kwds)

    def _sync(self, verbosity, output_fd, **kwds):
        raise NotImplementedError(self, "_sync")

    def __str__(self):
        return "%s syncer: %s, %s" % (self.__class__,
            self.basedir, self.uri)

    def _spawn(self, command, pipes):
        return spawn.spawn(command, fd_pipes=pipes)


def require_binary(bin_name, fatal=True):
    try:
        return spawn.find_binary(bin_name)
    except spawn.CommandNotFound:
        if fatal:
            raise
        return None


class syncer_exception(Exception):
    pass

class uri_exception(syncer_exception):
    pass
