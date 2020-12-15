"""
functionality to hand off to a callable, enabling collapsing
long chains of restrictions into Nlog N, or generating
restrictions on the fly
"""

__all__ = ("delegate",)

from . import restriction


class delegate(restriction.base):
    """hand off matching to a handed in prototype

    Example usage of this class should be available in
    :obj:`pkgcore.ebuild.domain`.
    """

    __slots__ = ('_transform', 'negate')

    type = restriction.package_type
    inst_caching = False

    def __init__(self, transform_func, negate=False):
        """
        :param transform_func: callable invoked with data, pkg, and mode
            mode may be "match", "force_True", or "force_False"
        """

        if not callable(transform_func):
            raise TypeError(transform_func)

        object.__setattr__(self, "negate", negate)
        object.__setattr__(self, "_transform", transform_func)

    def match(self, pkginst):
        return self._transform(pkginst, "match") != self.negate

    def force_True(self, pkginst):
        if self.negate:
            return self._transform(pkginst, "force_False")
        return self._transform(pkginst, "force_True")

    def force_False(self, pkginst):
        if self.negate:
            return self._transform(pkginst, "force_True")
        return self._transform(pkginst, "force_False")
