# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.repository.prototype import tree
from pkgcore.ebuild.cpv import CPV

class SimpleTree(tree):

    def __init__(self, cpv_dict, pkg_klass=None, livefs=False, frozen=True):
        self.cpv_dict = cpv_dict
        if pkg_klass is None:
            pkg_klass = CPV
        self.livefs = livefs
        self.package_class = pkg_klass
        tree.__init__(self, frozen=frozen)

    def _get_categories(self, *arg):
        if arg:
            return ()
        return tuple(self.cpv_dict.iterkeys())

    def _get_packages(self, category):
        return tuple(self.cpv_dict[category].iterkeys())

    def _get_versions(self, cp_key):
        return tuple(self.cpv_dict[cp_key[0]][cp_key[1]])

    def notify_remove_package(self, pkg):
        vers = self.cpv_dict[pkg.category][pkg.package]
        vers = [x for x in vers if x != pkg.fullver]
        if vers:
            self.cpv_dict[pkg.category][pkg.package] = vers
        else:
            del self.cpv_dict[pkg.category][pkg.package]
            if not self.cpv_dict[pkg.category]:
                del self.cpv_dict[pkg.category]
        tree.notify_remove_package(self, pkg)

    def notify_add_package(self, pkg):
        self.cpv_dict.setdefault(pkg.category,
            {}).setdefault(pkg.package, []).append(pkg.fullver)
        tree.notify_add_package(self, pkg)
