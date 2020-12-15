__all__ = (
    "PackageError", "InvalidPackageName", "MetadataException", "InvalidDependency",
    "ChksumError", "MissingChksum", "ParseChksumError",
)

import os

from ..exceptions import PkgcoreUserException


class PackageError(ValueError, PkgcoreUserException):
    """Generic package exception."""


class InvalidPackageName(PackageError):
    """Package name using unsupported characters or format."""

    def __init__(self, name, msg=None):
        self.name = name
        self.msg = msg

    def __str__(self):
        msg = self.name
        if self.msg is not None:
            msg += f': {self.msg}'
        return msg


class MetadataException(PackageError):
    """Generic package metadata exception."""

    def __init__(self, pkg, attr, error, verbose=None):
        super().__init__(f"metadata exception: pkg {pkg}, attr {attr}: {error}")
        self.pkg, self.attr, self.error, self.verbose = pkg, attr, error, verbose

    def msg(self, verbosity=0):
        """Extract error message from verbose output depending on verbosity level."""
        s = self.error
        if self.verbose:
            if verbosity > 0:
                s += ':\n'
            else:
                s += ': '
            s += self.verbose.msg(verbosity)
        return s


class InvalidDependency(PackageError):
    """Generic bad package dependency."""


class ChksumError(PkgcoreUserException):
    """Generic checksum failure."""


class MissingChksum(ChksumError):

    def __init__(self, pkg, filename):
        super().__init__(
            f"{pkg.cpvstr}::{pkg.repo} missing chksum data for {filename!r}")
        self.pkg = pkg
        self.file = filename


class ParseChksumError(ChksumError):

    def __init__(self, filename, error, missing=False):
        filename = os.sep.join(filename.split(os.sep)[-3:])
        if missing:
            super().__init__(
                f"failed parsing {filename!r}; data isn't available: {error}")
        else:
            super().__init__(f"failed parsing {filename!r}: {error}")
        self.file = filename
        self.error = error
        self.missing = missing
