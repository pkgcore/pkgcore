# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
base profile class- WARNING, may not be around long (provides little gain and is ebuild specific)
"""

class base(object):
    pass

class ProfileException(Exception):
    def __init__(self, err):
        self.err = err
    def __str__(self):
        return str(self.err)
