# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
exceptions thrown by chksum subsystem
"""

class base(Exception):
    pass

class MissingChksum(base):

    def __init__(self, filename):
        base.__init__(self, "Missing chksum file %r" % filename)
        self.file = filename


class ParseChksumError(base):
    def __init__(self, filename, error):
        base.__init__(self, "Failed parsing %r chksum due to %s" %
                      (filename, error))
        self.file, self.error = filename, error
