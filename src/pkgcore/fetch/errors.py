"""
errors fetch subsystem may throw
"""

from ..exceptions import PkgcoreUserException


class FetchError(PkgcoreUserException):
    """Generic fetch exception."""


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


class FetchFailed(FetchError):

    def __init__(self, filename, message, resumable=False):
        super().__init__(message)
        self.filename = filename
        self.message = message
        self.resumable = resumable

    def __str__(self):
        return f"failed fetching: {self.filename!r}: {self.message}"


class MissingDistfile(FetchFailed):

    def __init__(self, filename):
        super().__init__(filename, "doesn't exist", resumable=True)


class ChksumError(FetchError):
    """Generic checksum failure."""


class ChksumFailure(FetchFailed, ChksumError):
    """Checksum verification failed."""

    def __init__(self, filename, *, chksum, expected, value):
        self.filename = filename
        self.chksum = chksum
        self.expected = expected
        self.value = value
        super().__init__(filename, "checksum verification failed")


class RequiredChksumDataMissing(ChksumError):
    """A required checksum for the target is missing."""

    def __init__(self, fetchable, *chksum):
        super().__init__(
            f"chksum(s) {', '.join(chksum)} were configured as required, "
            f"but the data is missing: {fetchable.filename!r}"
        )
        self.fetchable, self.missing_chksum = fetchable, chksum


class MissingChksumHandler(ChksumError):
    """An unknown checksum type tried to be hashed."""
