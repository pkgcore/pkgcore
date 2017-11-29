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
                           "metadata exception: pkg %s, attr %s\nerror: %s" %
                           (pkg, attr, error))
        self.pkg, self.attr, self.error = pkg, attr, error

class InvalidDependency(PackageError):
    pass


class ChksumBase(Exception):
    pass

class MissingChksum(ChksumBase):

    def __init__(self, filename):
        ChksumBase.__init__(self, "missing chksum data for %r" % filename)
        self.file = filename

class ParseChksumError(ChksumBase):
    def __init__(self, filename, error, missing=False):
        if missing:
            ChksumBase.__init__(self, "failed parsing %r chksum; data isn't available: %s" %
                          (filename, error))
        else:
            ChksumBase.__init__(self, "failed parsing %r chksum due to %s" %
                          (filename, error))
        self.file = filename
        self.error = error
        self.missing = missing
