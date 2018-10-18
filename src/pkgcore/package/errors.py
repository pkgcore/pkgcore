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

    def __init__(self, pkg, attr, error):
        Exception.__init__(
            self, f"metadata exception: pkg {pkg}, attr {attr}\nerror: {error}")
        self.pkg, self.attr, self.error = pkg, attr, error


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
