# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
pkgset based around loading a list of atoms from a world file
"""

__all__ = ("FileList", "WorldFile")

from pkgcore.config import ConfigHint, errors
from pkgcore.ebuild import const
from pkgcore.ebuild.atom import atom
from pkgcore.package.errors import InvalidDependency
from snakeoil import compatibility, klass

from snakeoil.demandload import demandload
demandload(globals(),
    'snakeoil.fileutils:AtomicWriteFile,readlines_ascii',
    'pkgcore:os_data',
    'pkgcore.log:logger',
)

class FileList(object):
    pkgcore_config_type = ConfigHint({'location':'str'}, typename='pkgset')
    error_on_subsets = True

    def __init__(self, location, gid=os_data.portage_gid, mode=0644):
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
                        raise ValueError("set %s isn't a valid atom in pkgset %r" %
                            (x, self.path))
                    logger.warning("set item %r found in pkgset %r: it will be "
                        "wiped on update since portage/pkgcore store set items"
                        " in a seperate way" % (x[1:], self.path))
                    continue
                s.add(atom(x))
        except InvalidDependency, e:
            compatibility.raise_from(errors.ParsingError("parsing %r" % self.path, exception=e))

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
    pkgcore_config_type = ConfigHint(typename='pkgset')
    error_on_subsets = False

    def __init__(self, location=const.WORLD_FILE,
        gid=os_data.portage_gid, mode=0644):
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

