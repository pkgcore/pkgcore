# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
prototype fetcher class, all fetchers should derive from this
"""

__all__ = ("fetcher",)

import os
from snakeoil.chksum import get_handlers, get_chksums
from snakeoil import compatibility
from pkgcore.fetch import errors
from snakeoil.compatibility import cmp

class fetcher(object):

    def _verify(self, file_location, target, all_chksums=True, handlers=None):
        """
        Internal function for derivatives.

        Digs through chksums, and either returns None, or throws an
        errors.FetchFailed exception.
          - -2: file doesn't exist.
          - -1: if (size chksum is available, and
                file is smaller than stated chksum)
          - 0:  if all chksums match
          - 1:  if file is too large (if size chksums are available)
                or else size is right but a chksum didn't match.

        if all_chksums is True, all chksums must be verified; if false, all
        a handler can be found for are used.
        """

        nondefault_handlers = handlers
        if handlers is None:
            try:
                handlers = get_handlers(target.chksums)
            except KeyError, e:
                compatibility.raise_from(
                    errors.FetchFailed(file_location,
                        "Couldn't find a required checksum handler"))
        if all_chksums:
            missing = set(target.chksums).difference(handlers)
            if missing:
                raise errors.RequiredChksumDataMissing(target,
                    *sorted(missing))

        if "size" in handlers:
            val = handlers["size"](file_location)
            if val is None:
                raise errors.MissingDistfile(file_location)
            c = cmp(val, target.chksums["size"])
            if c:
                resumable = (c < 0)
                raise errors.FetchFailed(file_location,
                    "File is too small.", resumable=resumable)
        elif not os.path.exists(file_location):
            raise errors.MissingDistfile(file_location)

        chfs = set(target.chksums).intersection(handlers)
        chfs.discard("size")
        chfs = list(chfs)
        if nondefault_handlers:
            for x in chfs:
                val = handlers[x](file_location)
                if val != target.chksums[x]:
                    raise errors.FetchFailed(file_location,
                        "Validation handler %s: expected %s, got %s" % (
                        x, target.chksums[x], val))
        else:
            desired_vals = [target.chksums[x] for x in chfs]
            calced = get_chksums(file_location, *chfs)
            for desired, got, chf in zip(desired_vals, calced, chfs):
                if desired != got:
                    raise errors.FetchFailed(file_location,
                        "Validation handler %s: expected %s, got %s" % (
                        chf, desired, got))

    def __call__(self, fetchable):
        if not fetchable.uri:
            return self.get_path(fetchable)
        return self.fetch(fetchable)

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
