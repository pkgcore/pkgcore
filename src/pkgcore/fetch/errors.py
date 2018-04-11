# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
errors fetch subsystem may throw
"""

__all__ = (
    "FetchError", "DistdirPerms", "UnmodifiableFile", "UnknownMirror",
    "RequiredChksumDataMissing"
)


class FetchError(Exception):
    pass


class DistdirPerms(FetchError):
    def __init__(self, distdir, required):
        FetchError.__init__(
            self, "distdir '%s' required fs attributes weren't enforcable: %s"
            % (distdir, required))
        self.distdir, self.required = distdir, required


class UnmodifiableFile(FetchError):
    def __init__(self, filename, extra=''):
        FetchError.__init__(self, "Unable to update file %s, unmodifiable %s"
                      % (filename, extra))
        self.filename = filename


class UnknownMirror(FetchError):
    def __init__(self, host, uri):
        FetchError.__init__(self, "uri mirror://%s/%s isn't a known mirror tier"
                      % (host, uri))
        self.host, self.uri = host, uri


class RequiredChksumDataMissing(FetchError):
    def __init__(self, fetchable, *chksum):
        FetchError.__init__(self, "chksum(s) %s were configured as required, "
                      "but the data is missing from fetchable '%s'"
                      % (', '.join(chksum), fetchable))
        self.fetchable, self.missing_chksum = fetchable, chksum


class FetchFailed(FetchError):
    def __init__(self, filename, message, resumable=False):
        FetchError.__init__(self, message)
        self.filename = filename
        self.message = message
        self.resumable = resumable

    def __str__(self):
        return f"File {self.filename}: {self.message}"


class MissingDistfile(FetchFailed):
    def __init__(self, filename):
        FetchFailed.__init__(self, filename, "Doesn't exist.", resumable=True)


class MissingChksumHandler(FetchError):
    pass
