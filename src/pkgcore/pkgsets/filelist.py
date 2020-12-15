"""
pkgset based around loading a list of atoms from a world file
"""

__all__ = ("FileList", "WorldFile")

from snakeoil import klass
from snakeoil.fileutils import AtomicWriteFile, readlines_ascii

from .. import os_data
from ..config import errors
from ..config.hint import ConfigHint
from ..ebuild import const
from ..ebuild.atom import atom
from ..log import logger
from ..package.errors import InvalidDependency


class FileList:
    pkgcore_config_type = ConfigHint({'location': 'str'}, typename='pkgset')
    error_on_subsets = True

    def __init__(self, location, gid=os_data.portage_gid, mode=0o644):
        self.path = location
        self.gid = gid
        self.mode = mode
        # note that _atoms is generated on the fly.

    @klass.jit_attr
    def _atoms(self):
        try:
            s = set()
            for x in readlines_ascii(self.path, True):
                if not x or x.startswith("#"):
                    continue
                elif x.startswith("@"):
                    if self.error_on_subsets:
                        raise ValueError(
                            "set %s isn't a valid atom in pkgset %r" %
                            (x, self.path))
                    logger.warning(
                        "set item %r found in pkgset %r: it will be "
                        "wiped on update since portage/pkgcore store set items "
                        "in a separate way", x[1:], self.path)
                    continue
                s.add(atom(x))
        except InvalidDependency as e:
            raise errors.ParsingError("parsing %r" % self.path, exception=e) from e

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
        try:
            f = AtomicWriteFile(self.path, gid=self.gid, perms=self.mode)
            f.write("\n".join(str(x) for x in sorted(self._atoms)))
            f.close()
        except:
            if f is not None:
                f.discard()
            raise


class WorldFile(FileList):
    """Set of packages contained in the world file."""
    pkgcore_config_type = ConfigHint(typename='pkgset')
    error_on_subsets = False

    def __init__(self, location=const.WORLD_FILE,
                 gid=os_data.portage_gid, mode=0o644):
        FileList.__init__(self, location, gid=gid, mode=mode)

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
