# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
repository that combines multiple repositories together
"""

__all__ = ("tree", "operations")

from functools import partial
from itertools import chain
from operator import itemgetter

from snakeoil import klass
from snakeoil.compatibility import sorted_cmp
from snakeoil.currying import post_curry
from snakeoil.demandload import demandload
from snakeoil.iterables import iter_sort

from pkgcore.config import configurable
from pkgcore.operations import repo as repo_interface
from pkgcore.repository import prototype, errors

demandload('os')


class operations(repo_interface.operations_proxy):

    ops_stop_after_first_supported = frozenset(
        ["install", "uninstall", "replace"])

    @klass.cached_property
    def raw_operations(self):
        return frozenset(chain.from_iterable(
            tree.operations.raw_operations for tree in self.repo.trees))

    @klass.cached_property
    def enabled_operations(self):
        s = set(chain.from_iterable(
            tree.operations.enabled_operations for tree in self.repo.trees))
        return frozenset(self._apply_overrides(s))

    def _setup_api(self):
        for op in self.enabled_operations:
            setattr(self, op, partial(self._proxy_op, op))

    def _proxy_op(self, op_name, *args, **kwds):
        ret = singleton = object()
        for tree in self.repo.trees:
            ops = tree.operations
            if not ops.supports(op_name):
                continue
            # track the success for return.
            ret2 = getattr(ops, op_name)(*args, **kwds)
            if ret is singleton:
                ret = ret2
            else:
                ret = ret and ret2
            if op_name in self.ops_stop_after_first_supported:
                return ret
        if ret is singleton:
            raise NotImplementedError(self, op_name)
        return ret


@configurable({'repositories': 'refs:repo'}, typename='repo')
def config_tree(repositories):
    return tree(*repositories)


class tree(prototype.tree):
    """Repository combining multiple repositories together.

    Args:
        trees (list): :obj:`pkgcore.repository.prototype.tree` instances

    Attributes:
        frozen_settable (bool): controls whether frozen is able to be set
            on initialization
        operations_kls: callable to generate a repo operations instance

        trees (list): :obj:`pkgcore.repository.prototype.tree` instances
    """

    frozen_settable = False
    operations_kls = operations

    def __init__(self, *trees):
        super(tree, self).__init__()
        for x in trees:
            if not hasattr(x, 'itermatch'):
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

    def path_restrict(self, path):
        """Create a package restriction from a given path within a repo.

        Args:
            path (str): file path, usually to an ebuild or binpkg

        Returns:
            package restriction

        Raises:
            ValueError: path doesn't conform to correct repo layout
                format or isn't within the repo
        """
        for repo in self.trees:
            if path not in repo:
                continue
            try:
                return repo.path_restrict(path)
            except ValueError:
                raise
        raise ValueError("no repo contains: '%s'" % path)

    def repo_containing_path(self, path):
        """Find the repo containing a path.

        Args:
            path (str): path in the filesystem

        Returns:
            repo object if a matching repo is found, otherwise None.

        Raises:
            ValueError: path matches multiple repos
        """
        repos = [r for r in self.trees if path in r]

        if len(repos) == 1:
            return repos[0]
        elif len(repos) > 1:
            raise ValueError("multiple repos contain: '%s'" % path)
        else:
            return None

    def itermatch(self, restrict, **kwds):
        sorter = kwds.get("sorter", iter)
        if sorter is iter:
            return (match for repo in self.trees
                    for match in repo.itermatch(restrict, **kwds))

        # ugly, and a bit slow, but works.
        def f(x, y):
            l = sorter([x, y])
            if l[0] == y:
                return 1
            return -1
        f = post_curry(sorted_cmp, f, key=itemgetter(0))
        return iter_sort(
            f, *[repo.itermatch(restrict, **kwds) for repo in self.trees])

    itermatch.__doc__ = prototype.tree.itermatch.__doc__.replace(
        "@param", "@keyword").replace(":keyword restrict:", ":param restrict:")

    def __iter__(self):
        return (pkg for repo in self.trees for pkg in repo)

    def __len__(self):
        return sum(len(repo) for repo in self.trees)

    def __contains__(self, obj):
        if isinstance(obj, basestring):
            path = os.path.realpath(obj)
            if not os.path.exists(path):
                return False
            for repo in self.trees:
                try:
                    repo_path = os.path.realpath(getattr(repo, 'location'))
                except AttributeError:
                    continue
                if path.startswith(repo_path):
                    return True
            return False
        else:
            for pkg in self.itermatch(obj):
                return True
            return False

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
        neg, pos = set(), set()
        for tree in self.trees:
            data = tree._visibility_limiters()
            neg.update(data[0])
            pos.update(data[1])
        return [list(neg), list(pos)]

    @property
    def frozen(self):
        """bool: Repository mutability status."""
        return all(x.frozen for x in self.trees)
