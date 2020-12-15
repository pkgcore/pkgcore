"""
prototype fetcher class, all fetchers should derive from this
"""

__all__ = ("fetcher",)

import os

from snakeoil.chksum import MissingChksumHandler, get_chksums, get_handlers

from . import errors


class fetcher:

    def _verify(self, file_location, target, all_chksums=True, handlers=None):
        """Internal function for derivatives.

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
            except MissingChksumHandler as e:
                raise errors.MissingChksumHandler(
                    f'missing required checksum handler: {e}')
        if all_chksums:
            missing = set(target.chksums).difference(handlers)
            if missing:
                raise errors.RequiredChksumDataMissing(target, *sorted(missing))

        if "size" in handlers:
            val = handlers["size"](file_location)
            if val == -1:
                raise errors.MissingDistfile(file_location)
            if val != target.chksums["size"]:
                if val < target.chksums["size"]:
                    raise errors.FetchFailed(
                        file_location, 'file is too small', resumable=True)
                raise errors.ChksumFailure(
                    file_location, chksum='size', expected=target.chksums["size"], value=val)
        elif not os.path.exists(file_location):
            raise errors.MissingDistfile(file_location)
        elif not os.stat(file_location).st_size:
            raise errors.FetchFailed(
                file_location, 'file is empty', resumable=False)

        chfs = set(target.chksums).intersection(handlers)
        chfs.discard("size")
        chfs = list(chfs)
        if nondefault_handlers:
            for x in chfs:
                val = handlers[x](file_location)
                if val != target.chksums[x]:
                    raise errors.ChksumFailure(
                        file_location, chksum=x, expected=target.chksums[x], value=val)
        else:
            desired_vals = [target.chksums[x] for x in chfs]
            calced = get_chksums(file_location, *chfs)
            for desired, got, chf in zip(desired_vals, calced, chfs):
                if desired != got:
                    raise errors.ChksumFailure(
                        file_location, chksum=chf, expected=desired, value=got)

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
