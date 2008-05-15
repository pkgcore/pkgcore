# Copyright: 2006-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
pkgset based around loading a list of atoms from a world file
"""

import pkgcore.const
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.errors import MalformedAtom
from pkgcore.config import ConfigHint

from snakeoil.demandload import demandload
demandload(globals(),
    'snakeoil.fileutils:AtomicWriteFile',
    'snakeoil.osutils:readlines',
    'pkgcore:os_data',
    'pkgcore.log:logger',
)

class FileList(object):
    pkgcore_config_type = ConfigHint({'location':'str'}, typename='pkgset')
    error_on_subsets = True

    def __init__(self, location):
        self.path = location
        # note that _atoms is generated on the fly.

    def __getattr__(self, attr):
        if attr != "_atoms":
            raise AttributeError(attr)
        s = set()
        for x in readlines(self.path):
            x = x.strip()
            if not x or x.startswith("#"):
                continue
            elif x.startswith("@"):
                if self.error_on_subsets:
                    raise ValueError("set %s isn't a valid atom in pkgset %r" % 
                        (x, self.path))
                logger.warning("set item %r found in pkgset %r: it will be "
                    "wiped on update since portage/pkgcore store set items"
                    " in a seperate way" % (x[1:], self.path))
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
            f = AtomicWriteFile(self.path, gid=os_data.portage_gid, perms=0644)
            f.write("\n".join(map(str, sorted(self._atoms))))
            f.close()
        finally:
            del f


class WorldFile(FileList):
    pkgcore_config_type = ConfigHint(typename='pkgset')
    error_on_subsets = False

    def __init__(self, location=pkgcore.const.WORLD_FILE):
        FileList.__init__(self, location)

    def add(self, atom_inst):
        self._modify(atom_inst, FileList.add)

    def remove(self, atom_inst):
        self._modify(atom_inst, FileList.remove)

    def _modify(self, atom_inst, func):
        if atom_inst.slot:
            for slot in atom_inst.slot:
                if slot == '0':
                    new_atom_inst = atom(atom_inst.key)
                else:
                    new_atom_inst = atom(atom_inst.key + ":" + slot)
                func(self, new_atom_inst)
        else:
            atom_inst = atom(atom_inst.key)
            func(self, atom_inst)

