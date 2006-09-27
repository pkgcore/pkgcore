# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
pkgset based around loading a list of atoms from a world file
"""

from pkgcore.ebuild.atom import atom
from pkgcore.util.demandload import demandload
import pkgcore.const
demandload(globals(),
    "pkgcore.util.file:AtomicWriteFile ")

from pkgcore.config import ConfigHint

class FileList(object):
    pkgcore_config_type = ConfigHint({'location':'str'}, typename='pkgset')

    def __init__(self, location):
        self.path = location
        # note that _atoms is generated on the fly.

    def __getattr__(self, attr):
        if attr != "_atoms":
            raise AttributeError(attr)
        s = set()
        for x in open(self.path, "r"):
            x = x.strip()
            if not x:
                continue
            s.add(atom(x))
        self._atoms = s
        return s

    def __iter__(self):
        return iter(self._atoms)

    def __len__(self):
        return len(self._atoms)

    def __contains__(self, key):
        return key in self._atoms

    def add(self, atom_inst):
        self._atoms.add(atom_inst)
    
    def remove(self, atom_inst):
        self._atoms.remove(atom_inst)

    def flush(self):
        f = None
        # structured this way to force deletion (thus wiping) if something
        # fails.
        try:
            f = AtomicWriteFile(self.path)
            f.write("\n".join(map(str, self._atoms)))
            f.close()
        finally:
            del f


class WorldFile(FileList):
    pkgcore_config_type = ConfigHint(typename='pkgset')

    def __init__(self, location=pkgcore.const.WORLD_FILE):
        FileList.__init__(self, location)
    
    def add(self, atom_inst):
        atom_inst = atom(atom_inst.key)
        FileList.add(self, atom_inst)

    def remove(self, atom_inst):
        atom_inst = atom(atom_inst.key)
        FileList.remove(self, atom_inst)
        
