# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import operator
from pkgcore.restrictions import packages, values, restriction
from pkgcore.package.mutated import MutatedPkg
from pkgcore.util.iterables import caching_iter
from pkgcore.util.klass import GetAttrProxy

class nodeps_repo(object):
    default_depends = packages.AndRestriction(finalize=True)
    default_rdepends = packages.AndRestriction(finalize=True)
    def __init__(self, repo):
        self.raw_repo = repo

    def itermatch(self, *a, **kwds):
        return (MutatedPkg(x, overrides={"depends":self.default_depends,
                                         "rdepends":self.default_rdepends})
                for x in self.raw_repo.itermatch(*a, **kwds))

    def match(self, *a, **kwds):
        return list(self.itermatch(*a, **kwds))

    __getattr__ = GetAttrProxy("raw_repo")

    def __iter__(self):
        return self.itermatch(packages.AlwaysTrue)


class caching_repo(object):

    def __init__(self, db, strategy):
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
