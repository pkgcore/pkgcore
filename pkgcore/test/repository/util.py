# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.repository.prototype import tree
from pkgcore.ebuild.cpv import CPV

class SimpleTree(tree):
    package_class = staticmethod(CPV)
    def __init__(self, cpv_dict):
        self.cpv_dict = cpv_dict
        tree.__init__(self)

    def _get_categories(self, *arg):
        if arg:
            return ()
        return tuple(self.cpv_dict.iterkeys())

    def _get_packages(self, category):
        return tuple(self.cpv_dict[category].iterkeys())

    def _get_versions(self, cp_key):
        return tuple(self.cpv_dict[cp_key[0]][cp_key[1]])

