# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.demandload import demandload
demandload(globals(), "pkgcore:spawn os pwd")

class syncer(object):

    forcable=False
    
    def __init__(self, local_path, uri, default_verbosity=0):
        self.verbose = default_verbosity
        self.basedir = local_path.rstrip(os.path.sep) + os.path.sep
        self.uri = uri

    @staticmethod
    def split_users(raw_uri):
        """
        @param uri: string uri to split users from; harring::ferringb:pass
          for example is local user 'harring', remote 'ferringb',
          password 'pass'
        @return: (local user, remote user, remote pass), None for fields if 
          unset
        """
        uri = raw_uri.split("::", 1)
        if len(uri) == 1:
            return None, raw_uri
        try:
            if uri[1].startswith("@"):
                uri[1] = uri[1][1:]
            return pw.getpwnam(uri[0]).pw_uid, uri[1]
        except KeyError, e:
            raise missing_local_user(raw_uri, uri[0], e)
        
    
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
        return spawn.spawn(command, fd_pipes=pipes, uid=self.local_user)


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

class generic_exception(syncer_exception):
    pass

class missing_local_user(syncer_exception):
    pass
