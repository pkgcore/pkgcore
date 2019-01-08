# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

__all__ = (
    "PackageError", "InvalidPackageName", "MetadataException", "InvalidDependency",
    "ChksumBase", "MissingChksum", "ParseChksumError",
)


class PackageError(ValueError):
    pass


class InvalidPackageName(PackageError):
    pass


class MetadataException(PackageError):

    def __init__(self, pkg, attr, error, verbose=None):
        super().__init__(f"metadata exception: pkg {pkg}, attr {attr}\nerror: {error}")
        self.pkg, self.attr, self.error = pkg, attr, error
        self._verbose = verbose.strip('\n') if verbose else verbose

    def msg(self, verbosity=0):
        """Extract error message from verbose output depending on verbosity level."""
        s = self.error

        if self._verbose:
            if verbosity > 0:
                # add full bash output in verbose mode
                s += f":\n{self._verbose}"
            else:
                # extract context and die message from bash eerror output
                bash_error = [
                    x.lstrip(' *') for x in self._verbose.split('\n')
                    if x.startswith(' *')
                ]

                context = bash_error[-1]
                err_msg = bash_error[1]
                s += f": {context} \"{err_msg}\""

        return s


class InvalidDependency(PackageError):
    pass


class ChksumBase(Exception):
    pass


class MissingChksum(ChksumBase):

    def __init__(self, pkg, filename):
        ChksumBase.__init__(
            self, f"{pkg.cpvstr}::{pkg.repo} missing chksum data for {filename!r}")
        self.pkg = pkg
        self.file = filename


class ParseChksumError(ChksumBase):

    def __init__(self, filename, error, missing=False):
        if missing:
            ChksumBase.__init__(
                self, f"failed parsing {filename!r} chksum; data isn't available: {error}")
        else:
            ChksumBase.__init__(
                self, "failed parsing {filename!r} chksum due to {error}")
        self.file = filename
        self.error = error
        self.missing = missing
