# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
implementation of the standard PORTDIR + PORTDIR_OVERLAY repository stacking
"""

__all__ = ("OverlayRepo",)

from pkgcore.repository import prototype, multiplex
from pkgcore.config import ConfigHint, errors
from pkgcore.ebuild import repository
from pkgcore.ebuild.repo_objs import OverlayedLicenses

from itertools import chain

class OverlayRepo(prototype.tree):

    """
    Collapse multiple trees into one.

    Eclass dir is shared, the first package leftmost returned.
    """

    pkgcore_config_type = ConfigHint({'trees': 'refs:repo'}, typename='repo')

    configured = False
    configurables = ("domain", "settings",)
    configure = repository._ConfiguredTree

    operations_kls = multiplex.operations

    def __init__(self, trees, **kwds):
        """
        :param trees: :obj:`pkgcore.ebuild.repository._UnconfiguredTree` instances
            to combine.
        """

        if not trees or len(trees) < 2:
            raise errors.ComplexInstantiationError(
                "Must specify at least two pathes to ebuild trees to overlay")

        self.trees = tuple(trees)
        self._rv_trees = tuple(reversed(trees))
        self._version_owners = {}
        prototype.tree.__init__(self)
        self.licenses = OverlayedLicenses(*[t.licenses for t in trees if hasattr(t, 'licenses')])

    def _get_categories(self, category=None):
        if category is not None:
            updates = (tree.categories.get(category) for tree in self.trees)
            updates = [x for x in updates if x is not None]
            if not updates:
                raise KeyError(category)
        else:
            updates = [tree.categories for tree in self.trees]
        return tuple(set(chain(*updates)))

    def _get_packages(self, category):
        updates = (tree.packages.get(category) for tree in self.trees)
        updates = [x for x in updates if x is not None]
        if not updates:
            raise KeyError(category)
        return tuple(set(chain(*updates)))

    def _get_versions(self, catpkg):
        ver_owners = {}
        fails = 0
        for tree in self._rv_trees:
            new_vers = tree.versions.get(catpkg)
            if new_vers is not None:
                ver_owners.update((v, tree) for v in new_vers)
            else:
                fails += 1
        if fails == len(self._rv_trees):
            raise KeyError(catpkg)
        self._version_owners[catpkg] = tuple(ver_owners.iteritems())
        return tuple(ver_owners)

    def _internal_gen_candidates(self, candidates, sorter):
        for cp in candidates:
            if cp not in self.versions:
                self.versions.get(cp)
            for pkg in sorter(repo[cp + (ver,)]
                for ver, repo in self._version_owners.get(cp, ())):
                yield pkg

    def _visibility_limiters(self):
        s = set()
        for tree in self.trees:
            neg, pos = tree._visibility_limiters()
            s.update(pos)
            s.difference_update(neg)
        return [[], list(s)]
