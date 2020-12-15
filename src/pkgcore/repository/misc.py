__all__ = ("nodeps_repo", "caching_repo")

from snakeoil.iterables import caching_iter, iter_sort
from snakeoil.klass import DirProxy, GetAttrProxy

from ..ebuild.conditionals import DepSet
from ..operations.repo import operations_proxy
from ..package.mutated import MutatedPkg
from ..restrictions import packages


class nodeps_repo:
    """Repository wrapper that returns wrapped pkgs with deps wiped."""

    default_bdepend = default_depend = default_rdepend = default_pdepend = DepSet()

    def __init__(self, repo):
        """
        :param repo: repository to wrap
        """
        self.raw_repo = repo

    def itermatch(self, *a, **kwds):
        return (MutatedPkg(
            x, overrides={"bdepend": self.default_bdepend,
                          "depend": self.default_depend,
                          "rdepend": self.default_rdepend,
                          "pdepend": self.default_pdepend}
            )
            for x in self.raw_repo.itermatch(*a, **kwds))

    def match(self, *a, **kwds):
        return list(self.itermatch(*a, **kwds))

    __getattr__ = GetAttrProxy("raw_repo")
    __dir__ = DirProxy("raw_repo")

    def __iter__(self):
        return self.itermatch(packages.AlwaysTrue)


class restrict_repo:
    """Repository wrapper that skips packages matching a given restriction."""

    def __init__(self, restrict, repo):
        """
        :param restrict: package matching restriction
        :param repo: repository to wrap
        """
        self.raw_repo = repo
        self.restrict = restrict

    def itermatch(self, *a, **kwds):
        return (
            x for x in self.raw_repo.itermatch(*a, **kwds)
            if not self.restrict.match(x))

    def match(self, *a, **kwds):
        return list(self.itermatch(*a, **kwds))

    __getattr__ = GetAttrProxy("raw_repo")
    __dir__ = DirProxy("raw_repo")

    def __iter__(self):
        return self.itermatch(packages.AlwaysTrue)


class caching_repo:
    """Repository wrapper that overrides match, returning :obj:`caching_iter` instances.

    Itermatch is slaved to match, in other words iterating over the
    caching_iter.

    Main use for this is to cache results from query lookups;
    if matches restrict arg is in the cache, the caller gets a shared
    caching_iter sequence, which may already be fully loaded with pkg
    instances.

    This can boost random lookup time pretty nicely, while helping to
    hold instance in memory to avoid redoing work.

    Cost of this of course is that involved objects are forced to stay
    in memory till the cache is cleared.  General use, not usually what
    you want- if you're making a lot of random queries that are duplicates
    (resolver does this for example), caching helps.
    """

    operations_kls = operations_proxy

    def __init__(self, db, strategy):
        """
        :param db: an instance supporting the repository protocol to cache
          queries from.
        :param strategy: forced sorting strategy for results.  If you don't
          need sorting, pass in iter.
        """
        self.__db__ = db
        self.__strategy__ = strategy
        self.__cache__ = {}

    def match(self, restrict):
        v = self.__cache__.get(restrict)
        if v is None:
            v = self.__cache__[restrict] = \
                caching_iter(
                    self.__db__.itermatch(restrict, sorter=self.__strategy__))
        return v

    def itermatch(self, restrict):
        return iter(self.match(restrict))

    __getattr__ = GetAttrProxy("__db__")
    __dir__ = DirProxy("__db__")

    def clear(self):
        self.__cache__.clear()


class multiplex_sorting_repo:

    def __init__(self, sorter, repos):
        self.__repos__ = tuple(repos)
        self.__sorter__ = sorter

    def itermatch(self, restrict):
        repo_iters = [repo.itermatch(restrict) for repo in self.__repos__]
        return iter_sort(self.__sorter__, *repo_iters)

    def match(self, restrict):
        return list(self.itermatch(restrict))

    def has_match(self, restrict):
        for repo in self.__repos__:
            if repo.has_match(restrict):
                return True
        return False
