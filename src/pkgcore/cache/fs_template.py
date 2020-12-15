"""
template for fs based backends
"""

__all__ = ("FsBased",)

import os

from snakeoil.osutils import ensure_dirs, pjoin

from ..os_data import portage_gid
from . import base


class FsBased(base):
    """Template wrapping fs needed options.

    Provides _ensure_access as a way to attempt to ensure files have
    the specified owners/perms.
    """

    def __init__(self, location, label=None, **config):
        """
        throws InitializationError if needs args aren't specified

        :keyword gid: defaults to :obj:`pkgcore.os_data.portage_gid`,
            gid to force all entries to
        :keyword perms: defaults to 0665, mode to force all entries to"""

        for x, y in (("gid", portage_gid), ("perms", 0o664)):
            if x in config:
                setattr(self, f'_{x}', config[x])
                del config[x]
            else:
                setattr(self, f'_{x}', y)
        super().__init__(**config)

        if label is not None:
            location = pjoin(location, label.lstrip(os.path.sep))

        self.location = location

        self._mtime_used = 'mtime' == self.chf_type

    __init__.__doc__ = "\n".join(
        x.lstrip() for x in __init__.__doc__.split("\n") + [
            y.lstrip().replace("@param", "@keyword")
            for y in base.__init__.__doc__.split("\n")
            if "@param" in y])

    def _ensure_access(self, path, mtime=None):
        """Ensure access to a path.

        :param mtime: if specified change mtime to this value.
        :return: C{False} if unable to guarantee access, C{True} otherwise.
        """
        try:
            os.chown(path, -1, self._gid)
            os.chmod(path, self._perms)
            if mtime is not None:
                mtime = int(mtime)
                os.utime(path, (mtime, mtime))
        except EnvironmentError:
            return False
        return True

    def _ensure_dirs(self, path=None):
        """Make sure a path relative to C{self.location} exists."""
        if path is not None:
            path = pjoin(self.location, os.path.dirname(path))
        else:
            path = self.location
        return ensure_dirs(path, mode=0o775, minimal=False)
