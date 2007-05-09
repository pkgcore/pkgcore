# Copyright: 2005-2006 Brian harring <ferringb@gmail.com>
# License: GPL2

"""
virtual repository, pkgs generated via callable
"""

from pkgcore.repository import prototype
from pkgcore.package import virtual
from snakeoil.currying import partial


class tree(prototype.tree):

    factory_kls = staticmethod(virtual.factory)
    
    def __init__(self, livefs=False):
        """
        @param grab_virtuals_func: callable to get a package -> versions mapping
        @param livefs: is this a livefs repository?
        """
        prototype.tree.__init__(self)
        self.livefs = livefs
        vf = self.factory_kls(self)
        self.package_class = vf.new_package

    def _expand_vers(self, cp, ver):
        raise NotImplementedError(self, "_expand_vers")

    def _internal_gen_candidates(self, candidates, sorter):
        pkls = self.package_class
        for cp in candidates:
            for pkg in sorter(pkls(provider, cp[0], cp[1], ver)
                for ver in self.versions.get(cp, ())
                for provider in self._expand_vers(cp, ver)):
                yield pkg

    def _get_categories(self, *optional_category):
        # return if optional_category is passed... cause it's not yet supported
        if optional_category:
            return ()
        return ("virtual",)

    def _load_data(self):
        raise NotImplementedError(self, "_load_data")

    def _get_packages(self, category):
        if category != "virtual":
            raise KeyError("no %s category for this repository" % category)
        self._load_data()
        return self.packages[category]
