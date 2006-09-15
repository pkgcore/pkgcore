# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
pkgset based around loading a list of atoms from a world file
"""

from pkgcore.ebuild.atom import atom
import pkgcore.const
from pkgcore.config import ConfigHint

class FileList(object):
    pkgcore_config_type = ConfigHint(typename='pkgset')

    def __init__(self, location=pkgcore.const.WORLD_FILE):
        self.path = location
        # note that _atoms is generated on the fly.

    def __getattr__(self, attr):
        if attr != "_atoms":
            raise AttributeError(attr)
        self._atoms = set(atom(x.strip()) for x in open(self.path, "r"))
        return self._atoms

    def __iter__(self):
        return iter(self._atoms)

    def __len__(self):
        return len(self._atoms)

    def __contains__(self, key):
        return key in self._atoms
