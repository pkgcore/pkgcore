# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
errors fetch subsystem may throw
"""

__all__ = (
    "FetchError", "DistdirPerms", "UnmodifiableFile", "UnknownMirror",
    "RequiredChksumDataMissing"
)

from pkgcore.exceptions import PkgcoreCliException


class FetchError(PkgcoreCliException):
    """Generic fetch exception."""

    def __init__(self, msg):
        super().__init__(f'fetching failed: {msg}')


class DistdirPerms(FetchError):

    def __init__(self, distdir, required):
        super().__init__(
            f"distdir {distdir} required fs attributes "
            f"weren't enforcable: {required}"
        )
        self.distdir, self.required = distdir, required


class UnmodifiableFile(FetchError):

    def __init__(self, filename, extra=''):
        super().__init__(
            f'unable to update file {filename}, unmodifiable {extra}')
        self.filename = filename


class UnknownMirror(FetchError):

    def __init__(self, host, uri):
        super().__init__(f'unknown mirror tier: uri mirror://{host}/{uri}')
        self.host, self.uri = host, uri


class FetchFailed(FetchError):

    def __init__(self, filename, message, resumable=False):
        super().__init__(message)
        self.filename = filename
        self.message = message
        self.resumable = resumable

    def __str__(self):
        return f"file {self.filename}: {self.message}"


class MissingDistfile(FetchFailed):

    def __init__(self, filename):
        super().__init__(filename, "doesn't exist", resumable=True)


class ChksumError(FetchError):
    """Generic checksum failure."""

    def __init__(self, filename, *, chksum, expected, value):
        self.filename = filename
        self.chksum = chksum
        self.expected = expected
        self.value = value
        super().__init__(f"{chksum} checksum verification failed: {filename!r}")


class RequiredChksumDataMissing(ChksumError):
    """A required checksum for the target is missing."""

    def __init__(self, fetchable, *chksum):
        super().__init__(
            f"chksum(s) {', '.join(chksum)} were configured as required, "
            f"but the data is missing from fetchable '{fetchable}'"
        )
        self.fetchable, self.missing_chksum = fetchable, chksum


class MissingChksumHandler(FetchError):
    """An unknown checksum type tried to be hashed."""
