# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
implementation of the standard PORTDIR + PORTDIR_OVERLAY repository stacking
"""

from pkgcore.repository import prototype
from pkgcore.config import ConfigHint, errors
from pkgcore.ebuild import repository

from itertools import chain

class OverlayRepo(prototype.tree):

    """
    Collapse multiple trees into one.

    Eclass dir is shared, the first package leftmost returned.
    """

    pkgcore_config_type = ConfigHint({'trees': 'refs:repo'}, typename='repo')

    configured = False
    configurables = ("domain", "settings",)
    configure = repository.ConfiguredTree

    # sucks a bit, need to work something better out here
    format_magic = "ebuild_src"

    def __init__(self, trees, **kwds):
        """
        @param trees: L{pkgcore.ebuild.repository.UnconfiguredTree} instances
            to combine.
        """

        if not trees or len(trees) < 2:
            raise errors.InstantiationError(
                "Must specify at least two pathes to ebuild trees to overlay")

        self.trees = tuple(trees)
        self._rv_trees = tuple(reversed(trees))
        self._version_owners = {}
        prototype.tree.__init__(self)

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
        i = iter(self._rv_trees)
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
        return [x for r in self.trees for x in r.default_visibility_limiters]
