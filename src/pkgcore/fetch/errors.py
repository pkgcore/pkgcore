# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
errors fetch subsystem may throw
"""

__all__ = (
    "distdirPerms", "UnmodifiableFile", "UnknownMirror",
    "RequiredChksumDataMissing"
)


class distdirPerms(Exception):
    def __init__(self, distdir, required):
        Exception.__init__(
            self, "distdir '%s' required fs attributes weren't enforcable: %s"
            % (distdir, required))
        self.distdir, self.required = distdir, required


class UnmodifiableFile(Exception):
    def __init__(self, filename, extra=''):
        Exception.__init__(self, "Unable to update file %s, unmodifiable %s"
                      % (filename, extra))
        self.filename = filename


class UnknownMirror(Exception):
    def __init__(self, host, uri):
        Exception.__init__(self, "uri mirror://%s/%s isn't a known mirror tier"
                      % (host, uri))
        self.host, self.uri = host, uri


class RequiredChksumDataMissing(Exception):
    def __init__(self, fetchable, *chksum):
        Exception.__init__(self, "chksum(s) %s were configured as required, "
                      "but the data is missing from fetchable '%s'"
                      % (', '.join(chksum), fetchable))
        self.fetchable, self.missing_chksum = fetchable, chksum


class FetchFailed(Exception):
    def __init__(self, filename, message, resumable=False):
        Exception.__init__(self, message)
        self.filename = filename
        self.message = message
        self.resumable = resumable

    def __str__(self):
        return "File %s: %s" % (self.filename, self.message)


class MissingDistfile(FetchFailed):
    def __init__(self, filename):
        FetchFailed.__init__(self, filename, "Doesn't exist.", resumable=True)


class MissingChksumHandler(Exception):
    pass
