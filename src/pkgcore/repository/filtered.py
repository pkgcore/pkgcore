"""
filtering repository
"""

__all__ = ("tree",)

from itertools import filterfalse

from snakeoil.klass import DirProxy, GetAttrProxy

from ..operations.repo import operations_proxy
from ..restrictions import restriction
from . import errors, prototype


class tree(prototype.tree):
    """Filter existing repository based upon passed in restrictions."""

    operations_kls = operations_proxy

    def __init__(self, repo, restrict, sentinel_val=False):
        self.raw_repo = repo
        self.sentinel_val = sentinel_val
        if not hasattr(self.raw_repo, 'itermatch'):
            raise errors.InitializationError(
                f"{self.raw_repo} is not a repository tree derivative")
        if not isinstance(restrict, restriction.base):
            raise errors.InitializationError(f"{restrict} is not a restriction")
        self.restrict = restrict
        self.raw_repo = repo
        if sentinel_val:
            self._filterfunc = filter
        else:
            self._filterfunc = filterfalse

    def itermatch(self, restrict, **kwds):
        # note that this lets the repo do the initial filtering.
        # better design would to analyze the restrictions, and inspect
        # the repo, determine what can be done without cost
        # (determined by repo's attributes) versus what does cost
        # (metadata pull for example).
        return self._filterfunc(
            self.restrict.match, self.raw_repo.itermatch(restrict, **kwds))

    itermatch.__doc__ = prototype.tree.itermatch.__doc__.replace(
        "@param", "@keyword").replace(":keyword restrict:", ":param restrict:")

    def __len__(self):
        count = 0
        for i in self:
            count += 1
        return count

    __getattr__ = GetAttrProxy("raw_repo")
    __dir__ = DirProxy("raw_repo")

    def __getitem__(self, key):
        v = self.raw_repo[key]
        if self.restrict.match(v) != self.sentinel_val:
            raise KeyError(key)
        return v

    def __repr__(self):
        return '<%s raw_repo=%r restrict=%r sentinel=%r @%#8x>' % (
            self.__class__.__name__,
            getattr(self, 'raw_repo', 'unset'),
            getattr(self, 'restrict', 'unset'),
            getattr(self, 'sentinel_val', 'unset'),
            id(self))
