# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


class InvalidCPV(ValueError):
    """Raised if an invalid cpv was passed in.

    @ivar args: single-element tuple containing the invalid string.
    @type args: C{tuple}
    """

class MetadataException(Exception):

    def __init__(self, pkg, attr, error):
        Exception.__init__(self,
                           "Metadata Exception: pkg %s, attr %s\nerror: %s" %
                           (pkg, attr, error))
        self.pkg, self.attr, self.error = pkg, attr, error
