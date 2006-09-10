# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
template for fs based backends
"""

import os
from pkgcore.cache import template
from pkgcore.os_data import portage_gid
from pkgcore.fs.util import ensure_dirs

class FsBased(template.database):
    """Template wrapping fs needed options.

    Provides _ensure_access as a way to attempt to ensure files have
    the specified owners/perms.
    """

    def __init__(self, *args, **config):
        """
        throws InitializationError if needs args aren't specified

        @keyword gid: defaults to L{pkgcore.os_data.portage_gid},
            gid to force all entries to
        @keyword perms: defaults to 0665, mode to force all entries to"""

        for x, y in (("gid", portage_gid), ("perms", 0664)):
            if x in config:
                setattr(self, "_"+x, config[x])
                del config[x]
            else:
                setattr(self, "_"+x, y)
        super(FsBased, self).__init__(*args, **config)

        if self.label.startswith(os.path.sep):
            # normpath.
            self.label = os.path.sep + os.path.normpath(
                self.label).lstrip(os.path.sep)

        self._mtime_used = "_mtime_" in self._known_keys

    __init__.__doc__ = "\n".join(
        x.lstrip() for x in __init__.__doc__.split("\n") + [
            y.lstrip().replace("@param", "@keyword")
            for y in template.database.__init__.__doc__.split("\n")
            if "@param" in y])

    def _ensure_access(self, path, mtime=-1):
        """Ensure access to a path.

        @param mtime: if specified change mtime to this value.
        @return: C{False} if unable to guarantee access, C{True} otherwise.
        """
        try:
            os.chown(path, -1, self._gid)
            os.chmod(path, self._perms)
            if mtime:
                mtime = long(mtime)
                os.utime(path, (mtime, mtime))
        except (OSError, IOError):
            return False
        return True

    def _ensure_dirs(self, path=None):
        """Make sure a path relative to C{self.location} exists."""
        if path is not None:
            path = self.location + os.path.sep + os.path.dirname(path)
        else:
            path = self.location
        return ensure_dirs(path)

def gen_label(label):
    """Turn a user-defined label into something usable as a filename."""
    if label.find(os.path.sep) == -1:
        return label
    label = label.strip("\"").strip("'")
    label = os.path.join(*(label.rstrip(os.path.sep).split(os.path.sep)))
    tail = os.path.split(label)[1]
    return "%s-%X" % (tail, abs(label.__hash__()))
