__all__ = (
    "SyncError", "UriError", "MissingLocalUser", "MissingBinary",
    "Syncer", "ExternalSyncer", "VcsSyncer",
    "GenericSyncer", "DisabledSyncer", "AutodetectSyncer",
)

import os
import pwd
import stat

from snakeoil import process

from .. import os_data, plugin
from ..config.hint import ConfigHint, configurable
from ..exceptions import PkgcoreUserException


class SyncError(PkgcoreUserException):
    """Generic syncing error."""


class UriError(SyncError):

    def __init__(self, uri, msg):
        self.uri = uri
        self.msg = msg
        super().__init__(f"{msg}: {uri!r}")


class PathError(SyncError):

    def __init__(self, path, msg):
        self.path = path.rstrip(os.path.sep)
        self.msg = msg
        super().__init__(f"{msg}: {self.path!r}")


class MissingLocalUser(SyncError):

    def __init__(self, uri, msg):
        self.uri = uri
        self.msg = msg
        super().__init__(f"{msg}: {uri!r}")


class MissingBinary(SyncError):

    def __init__(self, binary, msg):
        self.binary = binary
        self.msg = msg
        super().__init__(f"{msg}: {binary!r}")


class Syncer:

    forcable = False

    supported_uris = ()
    supported_protocols = ()
    supported_exts = ()

    # plugin system uses this.
    disabled = False

    pkgcore_config_type = ConfigHint(
        {'path': 'str', 'uri': 'str', 'opts': 'str', 'usersync': 'bool'},
        typename='syncer')

    def __init__(self, path, uri, default_verbosity=0, usersync=False, opts=''):
        self.verbosity = default_verbosity
        self.usersync = usersync
        self.basedir = path.rstrip(os.path.sep) + os.path.sep
        uri = self.parse_uri(uri)
        self.uid, self.gid, self.uri = self.split_users(uri)
        self.opts = opts.split()

    @staticmethod
    def parse_uri(uri):
        """Return the real URI with any protocol prefix stripped."""
        return uri

    @classmethod
    def is_usable_on_filepath(cls, path):
        return None

    def split_users(self, raw_uri):
        """
        :param raw_uri: string uri to split users from; harring::ferringb:pass
          for example is local user 'harring', remote 'ferringb',
          password 'pass'
        :return: (local user, remote user, remote pass), defaults to the
            current process's uid if no local user specified
        """
        uri = raw_uri.split("::", 1)
        if len(uri) == 1:
            if self.usersync:
                if os.path.exists(self.basedir):
                    stat = os.stat(self.basedir)
                    uid = stat.st_uid
                    gid = stat.st_gid
                else:
                    uid = os_data.portage_uid
                    gid = os_data.portage_gid
            else:
                uid = os_data.uid
                gid = os_data.gid

            return uid, gid, raw_uri
        try:
            if uri[1].startswith("@"):
                uri[1] = uri[1][1:]
            if '/' in uri[0] or ':' in uri[0]:
                proto = uri[0].split("/", 1)
                proto[1] = proto[1].lstrip("/")
                uri[0] = proto[1]
                uri[1] = f"{proto[0]}//{uri[1]}"

            return pwd.getpwnam(uri[0]).pw_uid, os_data.gid, uri[1]
        except KeyError as e:
            raise MissingLocalUser(raw_uri, str(e))

    def sync(self, verbosity=None, force=False):
        if self.disabled:
            return False
        kwds = {}
        if self.forcable and force:
            kwds["force"] = True
        if verbosity is None:
            verbosity = self.verbosity
        # output_fd is harded coded as stdout atm.
        return self._sync(verbosity, 1, **kwds)

    def _sync(self, verbosity, output_fd, **kwds):
        raise NotImplementedError(self, "_sync")

    def __str__(self):
        return f"{self.__class__} syncer: {self.basedir}, {self.uri}"

    @classmethod
    def supports_uri(cls, uri):
        for prefix, level in cls.supported_uris:
            if uri.startswith(prefix):
                return level
        if uri.startswith(cls.supported_protocols) and uri.endswith(cls.supported_exts):
            return 1
        return 0


class ExternalSyncer(Syncer):

    """Base class for syncers that spawn a binary to do the the actual work."""

    binary = None

    # external env settings passed through to syncing commands
    env_whitelist = (
        'SSH_AUTH_SOCK',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.env = {v: os.environ[v] for v in self.env_whitelist if v in os.environ}

        if not hasattr(self, 'binary_path'):
            self.binary_path = self.require_binary(self.binary)

    @staticmethod
    def require_binary(bin_name, fatal=True):
        try:
            return process.find_binary(bin_name)
        except process.CommandNotFound as e:
            if fatal:
                raise MissingBinary(bin_name, str(e))
            return None

    @classmethod
    def _plugin_disabled_check(cls):
        disabled = getattr(cls, '_disabled', None)
        if disabled is None:
            path = getattr(cls, 'binary_path', None)
            if path is None:
                if cls.binary is None:
                    disabled = cls._disabled = True
                else:
                    disabled = cls._disabled = (
                        cls.require_binary(cls.binary, fatal=False) is None)
            else:
                disabled = cls._disabled = os.path.exists(path)
        return disabled

    def _spawn(self, command, pipes, **kwargs):
        return process.spawn.spawn(
            command, fd_pipes=pipes, uid=self.uid, gid=self.gid, env=self.env, **kwargs)

    @staticmethod
    def _rewrite_uri_from_stat(path, uri):
        chunks = uri.split("//", 1)
        if len(chunks) == 1:
            return uri
        try:
            return "%s//%s::%s" % (
                chunks[0], pwd.getpwuid(os.stat(path).st_uid)[0], chunks[1])
        except KeyError:
            # invalid uid, reuse the uri
            return uri


class VcsSyncer(ExternalSyncer):

    def _sync(self, verbosity, output_fd):
        try:
            st = os.stat(self.basedir)
        except FileNotFoundError:
            command = self._initial_pull() + self.opts
            chdir = None
        except EnvironmentError as e:
            raise PathError(self.basedir, e.strerror) from e
        else:
            if not stat.S_ISDIR(st.st_mode):
                raise PathError(self.basedir, "isn't a directory")
            command = self._update_existing() + self.opts
            chdir = self.basedir

        # we assume syncers support -v and -q for verbose and quiet output
        if verbosity < 0:
            command.append('-q')
        elif verbosity > 0:
            command.append('-' + 'v' * verbosity)

        ret = self._spawn(command, pipes={1: output_fd, 2: output_fd, 0: 0},
                          cwd=chdir)
        return ret == 0

    def _initial_pull(self):
        raise NotImplementedError(self, "_initial_pull")

    def _update_existing(self):
        raise NotImplementedError(self, "_update_existing")


@configurable(
    {'basedir': 'str', 'uri': 'str', 'usersync': 'bool', 'opts': 'str'},
    typename='syncer')
def GenericSyncer(basedir, uri, **kwargs):
    """Syncer using the plugin system to find a syncer based on uri."""
    plugins = list(
        (plug.supports_uri(uri), plug)
        for plug in plugin.get_plugins('syncer'))
    plugins.sort(key=lambda x: x[0])
    if not plugins or plugins[-1][0] <= 0:
        raise UriError(uri, "no known syncer support")
    # XXX this is random if there is a tie. Should we raise an exception?
    return plugins[-1][1](basedir, uri, **kwargs)


class DisabledSyncer(Syncer):

    disabled = True

    def __init__(self, path, uri=None, **kwargs):
        super().__init__(path, uri='', **kwargs)


@configurable({'basedir': 'str', 'usersync': 'bool'}, typename='syncer')
def AutodetectSyncer(basedir, **kwargs):
    for plug in plugin.get_plugins('syncer'):
        ret = plug.is_usable_on_filepath(basedir)
        if ret is not None:
            return plug(basedir, *ret, **kwargs)
    return DisabledSyncer(basedir, **kwargs)
