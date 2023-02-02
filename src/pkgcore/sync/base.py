__all__ = (
    "SyncError",
    "UriError",
    "MissingLocalUser",
    "MissingBinary",
    "Syncer",
    "ExternalSyncer",
    "VcsSyncer",
    "GenericSyncer",
    "DisabledSyncer",
    "AutodetectSyncer",
)

import os
import pwd
import stat
import sys
import typing
from importlib import import_module

from snakeoil import process

from .. import os_data
from ..config.hint import ConfigHint, configurable
from ..exceptions import PkgcoreUserException
from ..log import logger


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
        types={"path": "str", "uri": "str", "opts": "str", "usersync": "bool"},
        typename="syncer",
    )

    def __init__(self, path, uri, default_verbosity=0, usersync=False, opts=""):
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
            if not self.usersync:
                uid = os_data.uid
                gid = os_data.gid
            elif os.path.exists(self.basedir):
                stat = os.stat(self.basedir)
                uid = stat.st_uid
                gid = stat.st_gid
            else:
                uid = os_data.portage_uid
                gid = os_data.portage_gid

            return uid, gid, raw_uri
        try:
            if uri[1].startswith("@"):
                uri[1] = uri[1][1:]
            if "/" in uri[0] or ":" in uri[0]:
                proto = uri[0].split("/", 1)
                proto[1] = proto[1].lstrip("/")
                uri[0] = proto[1]
                uri[1] = f"{proto[0]}//{uri[1]}"

            return pwd.getpwnam(uri[0]).pw_uid, os_data.gid, uri[1]
        except KeyError as exc:
            raise MissingLocalUser(raw_uri, str(exc))

    def sync(self, verbosity: typing.Optional[int] = None, force=False):
        if self.disabled:
            return False
        kwds = {}
        if self.forcable and force:
            kwds["force"] = True
        if verbosity is None:
            verbosity = self.verbosity
        return self._sync(verbosity, **kwds)

    def _sync(self, verbosity: int, **kwds):
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
    env_whitelist = ("SSH_AUTH_SOCK",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.env = {v: os.environ[v] for v in self.env_whitelist if v in os.environ}

        if not hasattr(self, "binary_path"):
            self.binary_path = self.require_binary(self.binary)

    @staticmethod
    def require_binary(bin_name, fatal=True):
        try:
            return process.find_binary(bin_name)
        except process.CommandNotFound as exc:
            if fatal:
                raise MissingBinary(bin_name, str(exc))
            return None

    @classmethod
    def _plugin_disabled_check(cls):
        disabled = getattr(cls, "_disabled", None)
        if disabled is None:
            path = getattr(cls, "binary_path", None)
            if path is None:
                if cls.binary is None:
                    disabled = cls._disabled = True
                else:
                    disabled = cls._disabled = (
                        cls.require_binary(cls.binary, fatal=False) is None
                    )
            else:
                disabled = cls._disabled = os.path.exists(path)
        return disabled

    def _spawn(self, command, **kwargs):
        # Note: stderr is explicitly forced to stdout since that's how it was originally done.
        # This can be changed w/ a discussion.
        kwargs.setdefault("fd_pipes", {1: 1, 2: 1})
        logger.debug("sync invoking command %r, kwargs %r", command, kwargs)
        # since we're intermixing two processes writing to stdout/stderr- us, and what we're invoking-
        # force a flush to keep output from being interlaced.  This is not hugely optimal, but
        # the CLI/observability integration needs refactoring anyways.
        sys.stdout.flush()
        sys.stderr.flush()
        return process.spawn.spawn(
            command, uid=self.uid, gid=self.gid, env=self.env, **kwargs
        )

    def _spawn_interactive(self, command, **kwargs):
        # Note: stderr is explicitly forced to stdout since that's how it was originally done.
        # This can be changed w/ a discussion.
        return self._spawn(command, fd_pipes={0: 0, 1: 1, 2: 1}, **kwargs)

    @staticmethod
    def _rewrite_uri_from_stat(path, uri):
        chunks = uri.split("//", 1)
        if len(chunks) == 1:
            return uri
        try:
            return f"{chunks[0]}//{pwd.getpwuid(os.stat(path).st_uid)[0]}::{chunks[1]}"
        except KeyError:
            # invalid uid, reuse the uri
            return uri


class VcsSyncer(ExternalSyncer):
    def _sync(self, verbosity):
        try:
            st = os.stat(self.basedir)
        except FileNotFoundError:
            command = self._initial_pull() + self.opts
            chdir = None
        except EnvironmentError as exc:
            raise PathError(self.basedir, exc.strerror) from exc
        else:
            if not stat.S_ISDIR(st.st_mode):
                raise PathError(self.basedir, "isn't a directory")
            command = self._update_existing() + self.opts
            chdir = self.basedir

        # we assume syncers support -v and -q for verbose and quiet output
        if verbosity < 0:
            command.append("-q")
        elif verbosity > 0:
            command.append("-" + "v" * verbosity)

        ret = self._spawn_interactive(command, cwd=chdir)
        return ret == 0

    def _initial_pull(self):
        raise NotImplementedError(self, "_initial_pull")

    def _update_existing(self):
        raise NotImplementedError(self, "_update_existing")


def _load_syncers():
    syncers = ("bzr", "cvs", "darcs", "git", "git_svn", "hg", "sqfs", "svn", "tar")
    for syncer in syncers:
        try:
            syncer_cls: type[Syncer] = getattr(
                import_module(f"pkgcore.sync.{syncer}"), f"{syncer}_syncer"
            )
        except (ImportError, AttributeError):
            continue
        if syncer_cls.disabled:
            continue
        if (
            f := getattr(syncer_cls, "_plugin_disabled_check", None)
        ) is not None and f():
            continue
        yield syncer_cls


@configurable(
    types={"basedir": "str", "uri": "str", "usersync": "bool", "opts": "str"},
    typename="syncer",
)
def GenericSyncer(basedir, uri, **kwargs):
    """Syncer using the plugin system to find a syncer based on uri."""
    plugins = [(plug.supports_uri(uri), plug) for plug in _load_syncers()]
    plugins.sort(key=lambda x: x[0])
    if not plugins or plugins[-1][0] <= 0:
        raise UriError(uri, "no known syncer support")
    # XXX this is random if there is a tie. Should we raise an exception?
    return plugins[-1][1](basedir, uri, **kwargs)


class DisabledSyncer(Syncer):
    disabled = True

    def __init__(self, path, *args, **kwargs):
        super().__init__(path, uri="")


@configurable(types={"basedir": "str", "usersync": "bool"}, typename="syncer")
def DisabledSync(basedir, *args, **kwargs):
    return DisabledSyncer(basedir)


@configurable(types={"basedir": "str", "usersync": "bool"}, typename="syncer")
def AutodetectSyncer(basedir, **kwargs):
    for syncer_cls in _load_syncers():
        if args := syncer_cls.is_usable_on_filepath(basedir):
            return syncer_cls(basedir, *args, **kwargs)
    return DisabledSyncer(basedir, **kwargs)
