# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

#base class
class InvalidPackage(ValueError):
    pass


class MetadataException(Exception):

    def __init__(self, pkg, attr, error):
        Exception.__init__(self,
                           "Metadata Exception: pkg %s, attr %s\nerror: %s" %
                           (pkg, attr, error))
        self.pkg, self.attr, self.error = pkg, attr, error
