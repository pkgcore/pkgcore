# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

#base class

__all__ = ("PackageError", "InvalidPackageName", "MetadataException", "InvalidDependency",
    "ChksumBase", "MissingChksum", "ParseChksumError")

class PackageError(ValueError):
    pass

class InvalidPackageName(PackageError):
    pass

class MetadataException(PackageError):

    def __init__(self, pkg, attr, error):
        Exception.__init__(self,
                           "Metadata Exception: pkg %s, attr %s\nerror: %s" %
                           (pkg, attr, error))
        self.pkg, self.attr, self.error = pkg, attr, error

class InvalidDependency(PackageError):
    pass


class ChksumBase(Exception):
    pass

class MissingChksum(ChksumBase):

    def __init__(self, filename):
        ChksumBase.__init__(self, "Missing chksum data for %r" % filename)
        self.file = filename

class ParseChksumError(ChksumBase):
    def __init__(self, filename, error):
        ChksumBase.__init__(self, "Failed parsing %r chksum due to %s" %
                      (filename, error))
        self.file, self.error = filename, error
