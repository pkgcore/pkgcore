"""
filtering repository
"""

__all__ = ("tree",)

from itertools import filterfalse
import typing

from snakeoil.klass import DirProxy, GetAttrProxy, alias_method

from ..operations.repo import operations_proxy
from ..restrictions import restriction
from . import errors, prototype
from pkgcore.ebuild.restricts import CategoryDep
from pkgcore.ebuild.atom import atom


class tree(prototype.tree):
    """Filter existing repository based upon passed in restrictions."""

    operations_kls = operations_proxy

    def __init__(self, repo, restrict, sentinel_val=False):
        self.raw_repo = repo
        self.sentinel_val = sentinel_val
        if not hasattr(self.raw_repo, "itermatch"):
            raise errors.InitializationError(
                f"{self.raw_repo} is not a repository tree derivative"
            )
        if not isinstance(restrict, restriction.base):
            raise errors.InitializationError(f"{restrict} is not a restriction")
        self.restrict = restrict
        self.raw_repo = repo
        if sentinel_val:
            self._filterfunc = filter
        else:
            self._filterfunc = filterfalse
        super().__init__()

    def itermatch(self, restrict, **kwds):
        # note that this lets the repo do the initial filtering.
        # better design would to analyze the restrictions, and inspect
        # the repo, determine what can be done without cost
        # (determined by repo's attributes) versus what does cost
        # (metadata pull for example).
        return self._filterfunc(
            self.restrict.match, self.raw_repo.itermatch(restrict, **kwds)
        )

    itermatch.__doc__ = prototype.tree.itermatch.__doc__.replace(
        "@param", "@keyword"
    ).replace(":keyword restrict:", ":param restrict:")

    def __len__(self):
        count = 0
        for i in self:
            count += 1
        return count

    # note: for the _get_* methods they use itermatch which would typically
    # be a cycle; this class's itermatch is fully reliant on the raw repo
    # thus no cycle.

    # TODO: add support for .{category,package,version}.force_regen via custom class.  No code relies upon this,
    # but that functionality missing means the implementation has a known potential for developing a stale cache.
    _get_categories = alias_method("raw_repo.categories.__iter__")

    def _get_packages(self, category: str) -> typing.Iterable[str]:
        for package in self.raw_repo.packages[category]:
            if any(self.itermatch(atom(f"{category}/{package}"))):
                yield package

    def _get_versions(self, catpkg: tuple[str, str]) -> typing.Iterable[str]:
        return (pkg.fullver for pkg in self.itermatch(atom(f"{catpkg[0]}/{catpkg[1]}")))

    __getattr__ = GetAttrProxy("raw_repo")
    __dir__ = DirProxy("raw_repo")

    def __getitem__(self, key):
        v = self.raw_repo[key]
        if self.restrict.match(v) != self.sentinel_val:
            raise KeyError(key)
        return v

    def __repr__(self):
        return "<%s raw_repo=%r restrict=%r sentinel=%r @%#8x>" % (
            self.__class__.__name__,
            getattr(self, "raw_repo", "unset"),
            getattr(self, "restrict", "unset"),
            getattr(self, "sentinel_val", "unset"),
            id(self),
        )
