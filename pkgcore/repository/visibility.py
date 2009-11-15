# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
filtering repository
"""

from pkgcore.repository import prototype, errors
from pkgcore.restrictions.restriction import base
from pkgcore.interfaces.repo import operations_proxy
from snakeoil.klass import GetAttrProxy
# these tricks are to keep 2to3 from screwing up.
from itertools import ifilter, ifilterfalse as filterfalse
from snakeoil import compatibility
if compatibility.is_py3k:
    ifilter = filter

class filterTree(prototype.tree):

    """Filter existing repository based upon passed in restrictions."""

    operations_kls = operations_proxy

    def __init__(self, repo, restriction, sentinel_val=False):
        self.raw_repo = repo
        self.sentinel_val = sentinel_val
        if not hasattr(self.raw_repo, 'itermatch'):
            raise errors.InitializationError(
                "%s is not a repository tree derivative" % (self.raw_repo,))
        if not isinstance(restriction, base):
            raise errors.InitializationError(
                "%s is not a restriction" % (restriction,))
        self.restriction = restriction
        self.raw_repo = repo
        if sentinel_val:
            self._filterfunc = ifilter
        else:
            self._filterfunc = filterfalse

    def itermatch(self, restrict, **kwds):
        # note that this lets the repo do the initial filtering.
        # better design would to analyze the restrictions, and inspect
        # the repo, determine what can be done without cost
        # (determined by repo's attributes) versus what does cost
        # (metadata pull for example).
        return self._filterfunc(self.restriction.match,
            self.raw_repo.itermatch(restrict, **kwds))


    itermatch.__doc__ = prototype.tree.itermatch.__doc__.replace(
        "@param", "@keyword").replace("@keyword restrict:", "@param restrict:")

    def __len__(self):
        count = 0
        for i in self:
            count += 1
        return count

    __getattr__ = GetAttrProxy("raw_repo")

    def __getitem__(self, key):
        v = self.raw_repo[key]
        if self.restriction.match(v) != self.sentinel_val:
            raise KeyError(key)
        return v

    def __repr__(self):
        return '<%s raw_repo=%r restriction=%r sentinel=%r @%#8x>' % (
            self.__class__.__name__,
            getattr(self, 'raw_repo', 'unset'),
            getattr(self, 'restriction', 'unset'),
            getattr(self, 'sentinel_val', 'unset'),
            id(self))
