# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.sync import base
from pkgcore.config import ConfigHint
from pkgcore.util.demandload import demandload

demandload(globals(), "os socket")

class rsyncer(base.syncer):

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
    
    @staticmethod
    def parse_uri(raw_uri):
        if not raw_uri.startswith("rsync://"):
            raise base.uri_exception(raw_uri, "doesn't start with rsync://")
        # split on @ to discern the host from the other crap
        uri = raw_uri[len("rsync://"):]
        raw_host, uri = uri.split("/", 1)

        # drop any user:pass@...
        host = raw_host.split("@", 1)[-1]

        # drop port.
        host = host.split(":", 1)[0]
        return host, raw_host, uri
    
    def __init__(self, basedir, uri, timeout=default_timeout,
        compress=False, excludes=(), includes=(),
        retries=default_retries,
        extra_opts=[]):
        
        # rsync doesn't gets weird if / isn't trailing.
        basedir = basedir.rstrip(os.path.sep) + os.path.sep
        base.syncer.__init__(self, basedir, uri, 2)
        self.rsync_fp = base.require_binary("rsync")

        self.opts = list(self.default_opts)
        self.opts.extend(extra_opts)
        if compress:
            self.opts.append("--compress")
        self.opts.append("--timeout=%i" % timeout)
        self.excludes = list(self.default_excludes) + list(excludes)
        self.includes = list(self.default_includes) + list(includes)
        self.retries = int(retries)
        self.is_ipv6 = "--ipv6" in self.opts or "-6" in self.opts
        self.is_ipv6 = self.is_ipv6 and socket.has_ipv6
        self.hostname, self.raw_host, self.remote_path = self.parse_uri(uri)
    
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
            raise base.syncer_exception(self.hostname, family, e)
            
    
    def _sync(self, verbosity, output_fd):
        fd_pipes = {1:output_fd, 2:output_fd}
        opts = list(self.opts)
        opts.extend("--exclude=%s" % x for x in self.excludes)
        opts.extend("--include=%s" % x for x in self.includes)
        if verbosity == 0:
            opts.append("--quiet")
        if verbosity > 1:
            opts.append("--stats")
        if verbosity >= 2:
            opts.append("--progress")
        elif verbosity >= 3:
            opts.append("--verbose")
        
        # zip limits to the shortest iterable.
        for count, ip in zip(xrange(self.retries), self._get_ips()):
            o = [self.rsync_fp,
                "rsync://%s/%s" % (self.raw_host.replace(self.hostname, ip),
                    self.remote_path),
                 self.basedir,
                ] + opts
            ret = base.spawn.spawn(o, fd_pipes=fd_pipes)
            if ret == 0:
                return True
            elif ret == 1:
                # syntax error.
                raise base.syncer_exception(opts, "syntax error")
            elif ret == 11:
                raise base.syncer_exception("rsync returned error code of "
                    "11; this is an out of space exit code")
            else:
                print ret
