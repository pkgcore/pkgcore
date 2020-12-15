__all__ = ("rsync_syncer", "rsync_timestamp_syncer",)

import os
import socket
import tempfile
import time

from snakeoil.osutils import pjoin

from ..config.hint import ConfigHint
from . import base


class rsync_syncer(base.ExternalSyncer):

    default_excludes = ['/distfiles', '/local', '/packages']
    default_includes = []
    default_conn_timeout = 15
    default_opts = [
        '--recursive',
        '--delete',
        '--delete-delay',
        '--perms',
        '--times',
        '--compress',
        '--force',
        '--links',
        '--safe-links',
        '--stats',
        '--human-readable',
        '--timeout=180',
        '--whole-file', # this one probably shouldn't be a default
    ]

    default_retries = 5
    binary = "rsync"

    @classmethod
    def _parse_uri(cls, raw_uri):
        if not raw_uri.startswith("rsync://") and \
                not raw_uri.startswith("rsync+"):
            raise base.UriError(raw_uri, "doesn't start with rsync:// nor rsync+")

        if raw_uri.startswith("rsync://"):
            return None, raw_uri

        proto = raw_uri.split(":", 1)
        proto[0] = proto[0].split("+", 1)[1]
        cls.require_binary(proto[0])
        return proto[0], f"rsync:{proto[1]}"

    pkgcore_config_type = ConfigHint({
        'basedir': 'str', 'uri': 'str', 'conn_timeout': 'str', 'usersync': 'bool',
        'compress': 'bool', 'excludes': 'list', 'includes': 'list',
        'retries': 'str', 'opts': 'list', 'extra_opts': 'list', 'proxy': 'str'},
        typename='syncer')

    def __init__(self, basedir, uri, conn_timeout=default_conn_timeout,
                 usersync=False, compress=False, excludes=(), includes=(),
                 retries=default_retries, proxy=None,
                 opts=(), extra_opts=()):
        uri = uri.rstrip(os.path.sep) + os.path.sep
        self.rsh, uri = self._parse_uri(uri)
        super().__init__(basedir, uri, default_verbosity=1, usersync=usersync)
        self.hostname = self.parse_hostname(self.uri)
        if self.rsh:
            self.rsh = self.require_binary(self.rsh)
        self.opts = list(opts) if opts else list(self.default_opts)
        self.opts.extend(extra_opts)
        if compress:
            self.opts.append("--compress")
        self.opts.append("--contimeout=%i" % int(conn_timeout))
        self.excludes = list(self.default_excludes) + list(excludes)
        self.includes = list(self.default_includes) + list(includes)
        self.retries = int(retries)
        self.use_proxy = proxy is not None
        if self.use_proxy:
            self.env['RSYNC_PROXY'] = proxy
        self.is_ipv6 = "--ipv6" in self.opts or "-6" in self.opts
        self.is_ipv6 = self.is_ipv6 and socket.has_ipv6

    @staticmethod
    def parse_hostname(uri):
        return uri[len("rsync://"):].split("@", 1)[-1].split("/", 1)[0]

    def _get_ips(self):
        if self.use_proxy:
            # If we're using a proxy, name resolution is best left to the proxy.
            yield self.hostname
            return

        af_fam = socket.AF_INET
        if self.is_ipv6:
            af_fam = socket.AF_INET6
        try:
            for ipaddr in socket.getaddrinfo(
                    self.hostname, None, af_fam, socket.SOCK_STREAM):
                if ipaddr[0] == socket.AF_INET6:
                    yield f"[{ipaddr[4][0]}]"
                else:
                    yield ipaddr[4][0]
        except OSError as e:
            raise base.SyncError(
                f"DNS resolution failed for {self.hostname!r}: {e.strerror}")

    def _sync(self, verbosity, output_fd):
        fd_pipes = {1: output_fd, 2: output_fd}
        opts = list(self.opts)
        if self.rsh:
            opts.append("-e")
            opts.append(self.rsh)
        opts.extend(f"--exclude={x}" for x in self.excludes)
        opts.extend(f"--include={x}" for x in self.includes)
        if verbosity < 0:
            opts.append("--quiet")
        elif verbosity > 0:
            opts.extend('-v' for x in range(verbosity))

        # zip limits to the shortest iterable
        ret = None
        for count, ip in zip(range(self.retries), self._get_ips()):
            cmd = [self.binary_path,
                 self.uri.replace(self.hostname, ip, 1),
                 self.basedir] + opts

            ret = self._spawn(cmd, fd_pipes)
            if ret == 0:
                return True
            elif ret == 1:
                raise base.SyncError("rsync command syntax error: {' '.join(cmd)}")
            elif ret == 11:
                raise base.SyncError("rsync ran out of disk space")
           # need to do something here instead of just restarting...
           # else:
           #     print(ret)
        raise base.SyncError("all attempts failed")


class _RsyncFileSyncer(rsync_syncer):
    """Support syncing a single file over rsync."""

    def __init__(self, path, uri):
        super().__init__(basedir=path, uri=uri)
        # override parent classes that always assume directory syncing
        self.basedir = path
        self.uri = uri


class rsync_timestamp_syncer(rsync_syncer):

    forcable = True
    forward_sync_delay = 25 * 60 # 25 minutes
    negative_sync_delay = 60 * 60 # 60 minutes

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_timestamp = self.current_timestamp()

    def current_timestamp(self, path=None):
        """
        :param path: override the default path for the timestamp to read
        :return: string of the timestamp data
        """
        if path is None:
            path = pjoin(self.basedir, "metadata", "timestamp.chk")
        try:
            with open(path) as f:
                date, offset = f.read().strip().rsplit('+', 1)
            date = time.mktime(time.strptime(date, "%a, %d %b %Y %H:%M:%S "))
            # add the hour/minute offset
            date += int(offset[:2] * 60) + int(offset[2:])
            return date
        except (FileNotFoundError, NotADirectoryError):
            return None
        except ValueError:
            # malformed timestamp
            return None

    def _sync(self, verbosity, output_fd, force=False):
        doit = force or self.last_timestamp is None
        ret = None
        try:
            if not doit:
                # try to sync the timestamp file to check the delta
                with tempfile.NamedTemporaryFile() as new_timestamp:
                    timestamp_uri = pjoin(self.uri, "metadata", "timestamp.chk")
                    timestamp_path = new_timestamp.name
                    timestamp_syncer = _RsyncFileSyncer(timestamp_path, timestamp_uri)
                    ret = timestamp_syncer._sync(verbosity, output_fd)
                    if not ret:
                        doit = True
                    else:
                        delta = self.current_timestamp(timestamp_path) - self.last_timestamp
                        if delta >= 0:
                            doit = delta > self.forward_sync_delay
                        else:
                            doit = delta > self.negative_sync_delay
            if not doit:
                return True
            ret = super()._sync(verbosity, output_fd)
            # force a reset of the timestamp
            self.last_timestamp = self.current_timestamp()
        finally:
            if ret:
                return ret
            # ensure the timestamp is back to the old
            try:
                timestamp_path = pjoin(self.basedir, "metadata", "timestamp.chk")
                if self.last_timestamp is None:
                    os.remove(timestamp_path)
                else:
                    with open(timestamp_path, "w") as f:
                        f.write(time.strftime("%a, %d %b %Y %H:%M:%S +0000",
                                time.gmtime(self.last_timestamp)))
            except EnvironmentError:
                # don't care...
                pass
        return ret
