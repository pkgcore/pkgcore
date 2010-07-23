# Copyright: 2006-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.restrictions import packages
from pkgcore.package.mutated import MutatedPkg
from pkgcore.operations.repo import operations_proxy
from snakeoil.iterables import caching_iter
from snakeoil.klass import GetAttrProxy
from snakeoil.currying import partial
from snakeoil.iterables import iter_sort

__all__ = ("nodeps_repo", "caching_repo")

class nodeps_repo(object):

    """
    repository wrapper that returns wrapped pkgs via
    L{MutatedPkg} that have their depends/rdepends/post_rdepends wiped
    """

    default_depends = default_rdepends = default_post_rdepends = \
        packages.AndRestriction()

    def __init__(self, repo):
        """
        @param repo: repository to wrap
        """
        self.raw_repo = repo

    def itermatch(self, *a, **kwds):
        return (MutatedPkg(x,
            overrides={"depends":self.default_depends,
                "rdepends":self.default_rdepends,
                "post_rdepends":self.default_post_rdepends})
                for x in self.raw_repo.itermatch(*a, **kwds))

    def match(self, *a, **kwds):
        return list(self.itermatch(*a, **kwds))

    __getattr__ = GetAttrProxy("raw_repo")

    def __iter__(self):
        return self.itermatch(packages.AlwaysTrue)


class caching_repo(object):

    """
    repository wrapper that overrides match, returning
    L{caching_iter} instances; itermatch is slaved to match,
    in other words iterating over the caching_iter.

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
        @param db: an instance supporting the repository protocol to cache
          queries from.
        @param strategy: forced sorting strategy for results.  If you don't
          need sorting, pass in iter.
        """
        self.__db__ = db
        self.__strategy__ = strategy
        self.__cache__ = {}

    def match(self, restrict):
        v = self.__cache__.get(restrict)
        if v is None:
            v = self.__cache__[restrict] = \
                caching_iter(self.__db__.itermatch(restrict,
                    sorter=self.__strategy__))
        return v

    def itermatch(self, restrict):
        return iter(self.match(restrict))

    __getattr__ = GetAttrProxy("__db__")

    def clear(self):
        self.__cache__.clear()


class multiplex_sorting_repo(object):

    def __init__(self, sorter, *repos):
        self.__repos__ = repos
        self.__sorter__ = sorter

    def itermatch(self, restrict):
        return iter_sort(self.__sorter__,
            *[repo.itermatch(restrict) for repo in self.__repos__])

    def match(self, restrict):
        return list(self.itermatch(restrict))

    def has_match(self, restrict):
        for repo in self.__repos__:
            if repo.has_match(restrict):
                return True
        return False
