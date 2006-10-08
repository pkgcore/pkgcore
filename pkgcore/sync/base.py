# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.config import ConfigHint
from pkgcore.util.demandload import demandload
demandload(globals(), "pkgcore:spawn "
    "os pwd stat "
    "pkgcore:os_data ")

class syncer(object):

    forcable = False
    sets_env = False
    binary = None
    
    pkgcore_config_type = ConfigHint({'path':'str', 'uri':'str'},
        typename='syncer')
    
    def __init__(self, path, uri, default_verbosity=0):
        self.verbose = default_verbosity
        self.basedir = path.rstrip(os.path.sep) + os.path.sep
        self.local_user, self.uri = self.split_users(uri)
        if not self.sets_env:
            self.env = {}
        if not hasattr(self, 'binary_path'):
            self.binary_path = self.require_binary(self.binary)

    @staticmethod
    def split_users(raw_uri):
        """
        @param uri: string uri to split users from; harring::ferringb:pass
          for example is local user 'harring', remote 'ferringb',
          password 'pass'
        @return: (local user, remote user, remote pass), defaults to root_uid 
          if no local user specified
        """
        uri = raw_uri.split("::", 1)
        if len(uri) == 1:
            return os_data.root_uid, raw_uri
        try:
            if uri[1].startswith("@"):
                uri[1] = uri[1][1:]
            if '/' in uri[0] or ':' in uri[0]:
                proto = uri[0].split("/", 1)
                proto[1] = proto[1].lstrip("/")
                uri[0] = proto[1]
                uri[1] = "%s//%s" % (proto[0], uri[1])
            return pwd.getpwnam(uri[0]).pw_uid, uri[1]
        except KeyError, e:
            raise missing_local_user(raw_uri, uri[0], e)
    
    @staticmethod
    def require_binary(bin_name, fatal=True):
        try:
            return spawn.find_binary(bin_name)
        except spawn.CommandNotFound, e:
            if fatal:
                raise missing_binary(bin_name, e)
            return None

    def set_binary_path(self):
        self.binary_path = self.require_binary(self.binary)
    
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

    def _spawn(self, command, pipes, **kwargs):
        return spawn.spawn(command, fd_pipes=pipes, uid=self.local_user,
            env=self.env, **kwargs)


class dvcs_syncer(syncer):

    def _sync(self, verbosity, output_fd):
        try:
            st = os.stat(self.basedir)
        except (IOError, OSError), ie:
            if errno.ENOENT != ie.errno:
                raise base.generic_exception(self, self.basedir, ie)
            command = self._initial_pull()
            chdir = None
        else:
            if not stat.S_ISDIR(st.st_mode):
                raise base.generic_exception(self, self.basedir,
                    "isn't a directory")
            command = self._update_existing()
            chdir = self.basedir

        ret = self._spawn(command, {1:output_fd, 2:output_fd, 0:0},
            chdir=chdir)
        return ret

    def interpret_exit_code(self, val):
        return 0 == val
        
    def _initial_pull(self):
        raise NotImplementedError(self, "_initial_pull")
    
    def _update_existing(self):
        raise NotImplementedError(self, "_update_existing")        


class syncer_exception(Exception):
    pass

class uri_exception(syncer_exception):
    pass

class generic_exception(syncer_exception):
    pass

class missing_local_user(syncer_exception):
    pass

class missing_binary(syncer_exception):
    pass
