# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
prototype fetcher class, all fetchers should derive from this
"""

import os
from pkgcore.chksum import get_handlers
from pkgcore.fetch import errors


class fetcher(object):

    def _verify(self, file_location, target, required=None):
        """
        internal function for derivatives.

        digs through chksums, and returns:
          - -1: iff (size chksum is available, and
                file is smaller than stated chksum) or file doesn't exist.
          - 0:  iff all chksums match
          - 1:  iff file is too large (if size chksums are available)
                or else size is right but a chksum didn't match.

        if required is None, all chksums must match
        """
        if not os.path.exists(file_location):
            return -1

        handlers = get_handlers(target.chksums.keys())
        if required:
            for x in target.chksums:
                if x not in handlers:
                    raise errors.RequiredChksumDataMissing(target, x)

        if "size" in handlers:
            c = cmp(handlers["size"](file_location), target.chksums["size"])
            if c:
                if c < 0:
                    return -1
                return 1

        for x in handlers:
            if x != "size" or x not in handlers:
                if not handlers[x](file_location) == target.chksums[x]:
                    return 1

        return 0

    def __call__(self, *a, **kw):
        return self.fetch(*a, **kw)
