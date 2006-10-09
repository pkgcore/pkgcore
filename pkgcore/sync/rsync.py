# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.sync import base
from pkgcore.config import ConfigHint
from pkgcore.util.demandload import demandload

demandload(globals(), "os socket errno")

class rsync_syncer(base.ExternalSyncer):

    default_excludes = ["/distfiles", "/local", "/packages"]
    default_includes = []
    default_timeout = 180
    default_opts = ["--recursive",
        "--delete-after",
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
        proto[0] = proto[0].split("+",1)[1]
        cls.require_binary(proto[0])
        return proto[0], "rsync:%s" % proto[1]
    
    pkgcore_config_type = ConfigHint({'basedir':'str', 'uri':'str',
        'timeout':'str', 'compress':'bool', 'excludes':'list',
        'includes':'list', 'retries':'str', 'extra_opts':'list'},
        typename='syncer')

    def __init__(self, basedir, uri, timeout=default_timeout,
        compress=False, excludes=(), includes=(),
        retries=default_retries,
        extra_opts=[]):

        uri = uri.rstrip(os.path.sep) + os.path.sep
        self.rsh, uri = self.parse_uri(uri)
        base.ExternalSyncer.__init__(self, basedir, uri, 2)
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
        self.is_ipv6 = "--ipv6" in self.opts or "-6" in self.opts
        self.is_ipv6 = self.is_ipv6 and socket.has_ipv6

    @staticmethod
    def parse_hostname(uri):
        return uri[len("rsync://"):].split("@",1)[-1].split("/", 1)[0]
    
    def _get_ips(self):
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
            raise base.syncer_exception(self.hostname, af_fam, str(e))
            
    
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
            opts.append("--progress")
        if verbosity >= 2:
            opts.append("--stats")
        elif verbosity >= 3:
            opts.append("--verbose")
        
        # zip limits to the shortest iterable.
        for count, ip in zip(xrange(self.retries), self._get_ips()):
            o = [self.binary_path,
                self.uri.replace(self.hostname, ip),
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


class rsync_timestamp_syncer(rsync_syncer):
    
    forcable = True
    
    def __init__(self, *args, **kwargs):
        rsync_syncer.__init__(self, *args, **kwargs)
        self.last_timestamp = self.current_timestamp

    @property
    def current_timestamp(self):
        try:
            return open(os.path.join(self.basedir, "metadata",
                "timestamp.chk")).read().strip()
        except OSError, oe:
            if oe.errno != errno.ENOENT:
                raise
            return None
    
    def _sync(self, verbosity, output_fd, force=False):
        doit = force or self.last_timestamp is None
        if not doit:
            basedir = self.basedir
            uri = self.uri
            try:
                self.basedir += "/metadata/timestamp.chk"
                self.uri += "/metadata/timestamp.chk"
                ret = rsync_syncer._sync(self, verbosity, output_fd)
            finally:
                self.basedir = basedir
                self.uri = uri
            doit = ret == False or self.last_timestamp != self.current_timestamp
        if not doit:
            return True
        return rsync_syncer._sync(self, verbosity, output_fd)
