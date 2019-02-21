# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

__all__ = (
    "PackageError", "InvalidPackageName", "MetadataException", "InvalidDependency",
    "ChksumBase", "MissingChksum", "ParseChksumError",
)

from snakeoil import bash

from pkgcore.exceptions import PkgcoreUserException


class PackageError(ValueError, PkgcoreUserException):
    pass


class InvalidPackageName(PackageError):
    pass


class MetadataException(PackageError):

    def __init__(self, pkg, attr, error, verbose=None):
        super().__init__(f"metadata exception: pkg {pkg}, attr {attr}\nerror: {error}")
        self.pkg, self.attr, self.error = pkg, attr, error
        self.verbose = verbose.strip('\n') if verbose else verbose

    def msg(self, verbosity=0):
        """Extract error message from verbose output depending on verbosity level."""
        s = self.error

        if self.verbose:
            if verbosity > 0:
                # add full bash output in verbose mode
                s += f":\n{self.verbose}"
            else:
                # strip ANSI escapes from output
                lines = (bash.ansi_escape_re.sub('', x) for x in self.verbose.split('\n'))
                # extract context and die message from bash error output
                bash_error = [x.lstrip(' *') for x in lines if x.startswith(' *')]

                # append bash specific error message if it exists in the expected format
                if bash_error:
                    context = bash_error[-1]
                    err_msg = bash_error[1]
                    s += f": {context} \"{err_msg}\""

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
