# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import operator
from pkgcore.restrictions import packages, values, restriction
from pkgcore.package.mutated import MutatedPkg
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
