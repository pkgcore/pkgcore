# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
prototype fetcher class, all fetchers should derive from this
"""

import os
from pkgcore.chksum import get_handlers, get_chksums
from pkgcore.fetch import errors


class fetcher(object):

    def _verify(self, file_location, target, all_chksums=True, handlers=None):
        """
        internal function for derivatives.

        digs through chksums, and returns:
          - -1: iff (size chksum is available, and
                file is smaller than stated chksum) or file doesn't exist.
          - 0:  iff all chksums match
          - 1:  iff file is too large (if size chksums are available)
                or else size is right but a chksum didn't match.

        if all_chksums is True, all chksums must be verified; if false, all
        a handler can be found for are used.
        """
        if not os.path.exists(file_location):
            return -1

        nondefault_handlers = handlers
        if handlers is None:
            handlers = get_handlers(target.chksums)
        if all_chksums:
            for x in target.chksums:
                if x not in handlers:
                    raise errors.RequiredChksumDataMissing(target, x)

        if "size" in handlers:
            c = cmp(handlers["size"](file_location), target.chksums["size"])
            if c:
                if c < 0:
                    return -1
                return 1

        chfs = set(target.chksums).intersection(handlers)
        chfs.discard("size")
        chfs = list(chfs)
        if nondefault_handlers:
            for x in chfs:
                if not handlers[x](file_location) == target.chksums[x]:
                    return 1
        elif [target.chksums[x] for x in chfs] != \
            get_chksums(file_location, *chfs):
                return 1

        return 0

    def __call__(self, *a, **kw):
        return self.fetch(*a, **kw)
    
    def get_path(self, fetchable):
        """
        return the on disk path to a fetchable if it's available, and fully
        fetched.
        
        If it isn't, return None
        """
        raise NotImplementedError(self.get_path)

    def get_storage_path(self):
        """return the directory files are stored in
        returns None if not applicable
        """
        return None
