# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
repository that combines multiple repositories together
"""

from pkgcore.repository import prototype, errors
from pkgcore.util.currying import partial
from pkgcore.util.iterables import iter_sort
from operator import itemgetter

class tree(prototype.tree):

    """repository combining multiple repositories into one"""

    zero_index_grabber = itemgetter(0)

    def __init__(self, *trees):
        """
        @param trees: L{pkgcore.repository.prototype.tree} instances
            to combines into one
        """
        super(tree, self).__init__()
        for x in trees:
            if not isinstance(x, prototype.tree):
                raise errors.InitializationError(
                    "%s is not a repository tree derivative" % (x,))
        self.trees = trees

    def _get_categories(self, *optional_category):
        d = set()
        failures = 0
        if optional_category:
            optional_category = optional_category[0]
            for x in self.trees:
                try:
                    d.update(x.categories[optional_category])
                except KeyError:
                    failures += 1
        else:
            for x in self.trees:
                try:
                    map(d.add, x.categories)
                except (errors.TreeCorruption, KeyError):
                    failures += 1
        if failures == len(self.trees):
            if optional_category:
                raise KeyError("category base '%s' not found" %
                               str(optional_category))
            raise KeyError("failed getting categories")
        return tuple(d)

    def _get_packages(self, category):
        d = set()
        failures = 0
        for x in self.trees:
            try:
                d.update(x.packages[category])
            except (errors.TreeCorruption, KeyError):
                failures += 1
        if failures == len(self.trees):
            raise KeyError("category '%s' not found" % category)
        return tuple(d)

    def _get_versions(self, package):
        d = set()
        failures = 0
        for x in self.trees:
            try:
                d.update(x.versions[package])
            except (errors.TreeCorruption, KeyError):
                failures += 1

        if failures == len(self.trees):
            raise KeyError("category '%s' not found" % package)
        return tuple(d)

    def itermatch(self, restrict, **kwds):
        sorter = kwds.get("sorter", None)
        if sorter is None or sorter is iter:
            return (match for repo in self.trees
                for match in repo.itermatch(restrict, **kwds))
        # ugly, and a bit slow, but works.
        def f(x, y):
            l = sorter([x, y])
            if l[0] == y:
                return 1
            return -1
        f = partial(sorted, cmp=f)
        return iter_sort(f,
            *[repo.itermatch(restrict, **kwds) for repo in self.trees])

    itermatch.__doc__ = prototype.tree.itermatch.__doc__.replace(
        "@param", "@keyword").replace("@keyword restrict:", "@param restrict:")

    def __iter__(self):
        return (pkg for repo in self.trees for pkg in repo)

    def __len__(self):
        return sum(len(repo) for repo in self.trees)

    def __getitem__(self, key):
        for t in self.trees:
            try:
                p = t[key]
                return p
            except KeyError:
                pass
        # made it here, no match.
        raise KeyError("package %s not found" % key)

    def __repr__(self):
        return '<%s.%s trees=%r @%#8x>' % (
            self.__class__.__module__, self.__class__.__name__,
            getattr(self, 'trees', 'unset'),
            id(self))

    def _visibility_limiters(self):
        return [x for r in self.trees for x in r.default_visibility_limiters]
