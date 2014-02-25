# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

__all__ = ("rsync_syncer", "rsync_timestamp_syncer",)

from pkgcore.sync import base
from pkgcore.config import ConfigHint
from snakeoil.demandload import compatibility, demandload

demandload(globals(),
    'os',
    'socket',
    'errno',
    'snakeoil.osutils:pjoin',
    'time',
)

class rsync_syncer(base.ExternalSyncer):

    default_excludes = ["/distfiles", "/local", "/packages"]
    default_includes = []
    default_timeout = 180
    default_opts = ["--recursive",
        "--delete-delay",
        "--perms",
        "--times",
        "--force",
        "--safe-links",
        "--whole-file"] # this one probably shouldn't be a default.

    default_retries = 5
    binary = "rsync"

    @classmethod
    def parse_uri(cls, raw_uri):
        if not raw_uri.startswith("rsync://") and \
            not raw_uri.startswith("rsync+"):
            raise base.uri_exception(raw_uri,
                "doesn't start with rsync:// nor rsync+")

        if raw_uri.startswith("rsync://"):
            return None, raw_uri

        proto = raw_uri.split(":", 1)
        proto[0] = proto[0].split("+", 1)[1]
        cls.require_binary(proto[0])
        return proto[0], "rsync:%s" % proto[1]

    pkgcore_config_type = ConfigHint({'basedir':'str', 'uri':'str',
        'timeout':'str', 'compress':'bool', 'excludes':'list',
        'includes':'list', 'retries':'str', 'extra_opts':'list',
        'proxy':'str'},
        typename='syncer')

    def __init__(self, basedir, uri, timeout=default_timeout,
                 compress=False, excludes=(), includes=(),
                 retries=default_retries, proxy=None,
                 extra_opts=()):
        uri = uri.rstrip(os.path.sep) + os.path.sep
        self.rsh, uri = self.parse_uri(uri)
        base.ExternalSyncer.__init__(self, basedir, uri, default_verbosity=1)
        self.hostname = self.parse_hostname(self.uri)
        if self.rsh:
            self.rsh = self.require_binary(self.rsh)
        self.opts = list(self.default_opts)
        self.opts.extend(extra_opts)
        if compress:
            self.opts.append("--compress")
        self.opts.append("--timeout=%i" % int(timeout))
        self.excludes = list(self.default_excludes) + list(excludes)
        self.includes = list(self.default_includes) + list(includes)
        self.retries = int(retries)
        self.use_proxy = proxy is not None
        if self.use_proxy:
            self.sets_env = True
            self.env = {'RSYNC_PROXY':proxy}
        self.is_ipv6 = "--ipv6" in self.opts or "-6" in self.opts
        self.is_ipv6 = self.is_ipv6 and socket.has_ipv6

    @staticmethod
    def parse_hostname(uri):
        return uri[len("rsync://"):].split("@", 1)[-1].split("/", 1)[0]

    def _get_ips(self):
        if self.use_proxy:
            # If we're using a proxy, name resolution is best left to the proxy
            yield self.hostname
            return

        af_fam = socket.AF_INET
        if self.is_ipv6:
            af_fam = socket.AF_INET6
        try:
            for ipaddr in socket.getaddrinfo(self.hostname, None, af_fam,
                socket.SOCK_STREAM):
                if ipaddr[0] == socket.AF_INET6:
                    yield "[%s]" % ipaddr[4][0]
                else:
                    yield ipaddr[4][0]

        except socket.error, e:
            compatibility.raise_from(
                base.syncer_exception(self.hostname, af_fam, str(e)))


    def _sync(self, verbosity, output_fd):
        fd_pipes = {1:output_fd, 2:output_fd}
        opts = list(self.opts)
        if self.rsh:
            opts.append("-e")
            opts.append(self.rsh)
        opts.extend("--exclude=%s" % x for x in self.excludes)
        opts.extend("--include=%s" % x for x in self.includes)
        if verbosity == 0:
            opts.append("--quiet")
        if verbosity >= 1:
            opts.append("--stats")
        if verbosity >= 2:
            opts.append("-v")
        elif verbosity >= 3:
            opts.append("-v")

        # zip limits to the shortest iterable.
        ret = None
        for count, ip in zip(xrange(self.retries), self._get_ips()):
            o = [self.binary_path,
                self.uri.replace(self.hostname, ip, 1),
                self.basedir] + opts

            ret = self._spawn(o, fd_pipes)
            if ret == 0:
                return True
            elif ret == 1:
                # syntax error.
                raise base.syncer_exception(o, "syntax error")
            elif ret == 11:
                raise base.syncer_exception("rsync returned error code of "
                    "11; this is an out of space exit code")
           # need to do something here instead of just restarting...
           # else:
           #     print ret
        raise base.syncer_exception(ret, "all attempts failed")


class rsync_timestamp_syncer(rsync_syncer):

    forcable = True
    forward_sync_delay = 25 * 60 # 25 minutes
    negative_sync_delay = 60 * 60 # 60 minutes

    def __init__(self, *args, **kwargs):
        rsync_syncer.__init__(self, *args, **kwargs)
        self.last_timestamp = self.current_timestamp()

    def current_timestamp(self, path=None):
        """
        :param path: override the default path for the timestamp to read
        :return: string of the timestamp data
        """
        if path is None:
            path = pjoin(self.basedir, "metadata", "timestamp.chk")
        try:
            date, offset = open(path).read().strip().rsplit('+', 1)
            date = time.mktime(time.strptime(date, "%a, %d %b %Y %H:%M:%S "))
            # add the hour/minute offset.
            date += int(offset[:2] * 60) + int(offset[2:])
            return date
        except IOError, oe:
            if oe.errno not in (errno.ENOENT, errno.ENOTDIR):
                raise
            return None
        except ValueError:
            # malformed timestamp.
            return None

    def _sync(self, verbosity, output_fd, force=False):
        doit = force or self.last_timestamp is None
        ret = None
        try:
            if not doit:
                basedir = self.basedir
                uri = self.uri
                new_timestamp = pjoin(self.basedir, "metadata",
                    ".tmp.timestamp.chk")
                try:
                    self.basedir = new_timestamp
                    self.uri = pjoin(self.uri, "metadata", "timestamp.chk")
                    ret = rsync_syncer._sync(self, verbosity, output_fd)
                finally:
                    self.basedir = basedir
                    self.uri = uri
                if not ret:
                    doit = True
                else:
                    delta = self.current_timestamp(new_timestamp) - \
                        self.last_timestamp
                    if delta >= 0:
                        doit = delta > self.forward_sync_delay
                    else:
                        doit = delta > self.negative_sync_delay
            if not doit:
                return True
            ret = rsync_syncer._sync(self, verbosity, output_fd)
            # force a reset of the timestamp.
            self.last_timestamp = self.current_timestamp()
        finally:
            if ret is not None:
                if ret:
                    return ret
            # ensure the timestamp is back to the old.
            try:
                path = pjoin(self.basedir, "metadata", "timestamp.chk")
                if self.last_timestamp is None:
                    os.remove(path)
                else:
                    open(pjoin(self.basedir, "metadata", "timestamp.chk"),
                        "w").write(time.strftime("%a, %d %b %Y %H:%M:%S +0000",
                            time.gmtime(self.last_timestamp)))
            except EnvironmentError:
                # don't care...
                pass
        return ret
