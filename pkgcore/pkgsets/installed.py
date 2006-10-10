# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.restrictions import packages, values
from pkgcore.config import ConfigHint


class installed(object):

    """
    pkgset holding slotted_atoms of all installed pkgs
    """
    
    pkgcore_config_type = ConfigHint({'vdb': 'refs:repo'}, typename='pkgset')
    
    def __init__(self, vdb):
        self.vdbs = vdb
    
    def __iter__(self):
        restrict = packages.PackageRestriction("package_is_real",
            values.EqualityMatch(True))
        for repo in self.vdbs:
            for pkg in repo.itermatch(restrict):
                yield pkg.slotted_atom
