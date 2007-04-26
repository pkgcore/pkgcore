# Copyright: 2005-2006 Brian harring <ferringb@gmail.com>
# License: GPL2

"""
virtual repository, pkgs generated via callable
"""

from pkgcore.repository import prototype
from pkgcore.package import virtual
from snakeoil.currying import partial

def mangle_args(new_package_func, mangler_func, *args):
    return new_package_func(*mangler_func(args))

class tree(prototype.tree):

    factory_kls = staticmethod(virtual.factory)
    
    def __init__(self, grab_virtuals_func, livefs=False, pkg_args_mangler=None):
        """
        @param grab_virtuals_func: callable to get a package -> versions mapping
        @param livefs: is this a livefs repository?
        """
        super(tree, self).__init__()
        self.livefs = livefs
        if not callable(grab_virtuals_func):
            if not hasattr(grab_virtuals_func, "__getitem__"):
                raise TypeError("grab_virtuals_func must be a callable")
            else:
                self._virtuals = grab_virtuals_func
                self._grab_virtuals = None
        else:
            self._grab_virtuals = grab_virtuals_func

        vf = self.factory_kls(self)

        if pkg_args_mangler:
            self.package_class = partial(mangle_args, vf.new_package,
                pkg_args_mangler)
        else:
            self.package_class = vf.new_package

    def __getattr__(self, attr):
        if attr == '_virtuals':
            v = self._virtuals = self._grab_virtuals()
            self._grab_virtuals = None
            return v
        return prototype.tree.__getattr__(self, attr)

    def _fetch_metadata(self, pkg):
        return self._virtuals[pkg.package][pkg.fullver]

    def _get_categories(self, *optional_category):
        # return if optional_category is passed... cause it's not yet supported
        if optional_category:
            return ()
        return ("virtual",)

    def _get_packages(self, category):
        if category != "virtual":
            raise KeyError("no %s category for this repository" % category)

        return tuple(self._virtuals.iterkeys())

    def _get_versions(self, catpkg):
        if catpkg[0] == "virtual":
            return tuple(self._virtuals[catpkg[1]].iterkeys())
        raise KeyError("no '%s' package in this repository" % catpkg)
