# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
functionality to hand off to a callable, enabling collapsing
long chains of restrictions into Nlog N, or generating
restrictions on the fly
"""

__all__ = ("delegate")
from pkgcore.restrictions import restriction
from pkgcore.restrictions import packages

class delegate(restriction.base):

    """
    hand off matching to a handed in prototype
    
    Example usage of this class should be available in
    L{pkgcore.ebuild.domain}.
    """

    __slots__ = ("_transform", "_data")
    type = packages.package_type
    inst_caching = False

    def __init__(self, transform_func, data, negate=False):
        """

        @param transform_func: callable inovked with data, pkg, and mode
            mode may be "match", "force_true", or "force_false"
        @param data: data to pass to the transforming func
        """

        if not callable(transform_func):
            raise TypeError(transform_func)

        object.__setattr__(self, "negate", negate)
        object.__setattr__(self, "_transform", transform_func)
        object.__setattr__(self, "_data", data)


    def match(self, pkginst):
        return self._transform(self._data, pkginst, "match") != self.negate

    def force_true(self, pkginst):
        if self.negate:
            return self._transform(self._data, pkginst, "force_false")
        return self._transform(self._data, pkginst, "force_true")

    def force_true(self, pkginst):
        if self.negate:
            return self._transform(self._data, pkginst, "force_true")
        return self._transform(self._data, pkginst, "force_false")
