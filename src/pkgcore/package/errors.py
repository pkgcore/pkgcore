# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

__all__ = (
    "PackageError", "InvalidPackageName", "MetadataException", "InvalidDependency",
    "ChksumBase", "MissingChksum", "ParseChksumError",
)

from pkgcore.exceptions import PkgcoreUserException


class PackageError(ValueError, PkgcoreUserException):
    pass


class InvalidPackageName(PackageError):
    pass


class MetadataException(PackageError):

    def __init__(self, pkg, attr, error, verbose=None):
        super().__init__(f"metadata exception: pkg {pkg}, attr {attr}\nerror: {error}")
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


class ChksumBase(PkgcoreUserException):
    """Generic checksum failure."""


class MissingChksum(ChksumBase):

    def __init__(self, pkg, filename):
        super().__init__(
            f"{pkg.cpvstr}::{pkg.repo} missing chksum data for {filename!r}")
        self.pkg = pkg
        self.file = filename


class ParseChksumError(ChksumBase):

    def __init__(self, filename, error, missing=False):
        if missing:
            super().__init__(
                f"failed parsing {filename!r} chksum; data isn't available: {error}")
        else:
            super().__init__(
                f"failed parsing {filename!r} chksum due to {error}")
        self.file = filename
        self.error = error
        self.missing = missing
