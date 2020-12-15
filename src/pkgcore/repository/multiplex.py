"""
repository that combines multiple repos together
"""

__all__ = ("tree", "operations")

import os
from functools import partial
from itertools import chain
from operator import itemgetter

from snakeoil import klass
from snakeoil.compatibility import sorted_cmp
from snakeoil.currying import post_curry
from snakeoil.iterables import iter_sort

from ..config.hint import configurable
from ..operations import repo as repo_interface
from . import errors, prototype


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


@configurable({'repos': 'refs:repo'}, typename='repo')
def config_tree(repos):
    return tree(*repos)


class tree(prototype.tree):
    """Repository combining multiple repos together.

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
        super().__init__()
        for x in trees:
            if not hasattr(x, 'itermatch'):
                raise errors.InitializationError(
                    f'{x} is not a repository tree derivative')
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
                    list(map(d.add, x.categories))
                except (errors.RepoError, KeyError):
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
            except (errors.RepoError, KeyError):
                failures += 1
        if failures == len(self.trees):
            raise KeyError(f'category {category!r} not found')
        return tuple(d)

    def _get_versions(self, package):
        d = set()
        failures = 0
        for x in self.trees:
            try:
                d.update(x.versions[package])
            except (errors.RepoError, KeyError):
                failures += 1

        if failures == len(self.trees):
            raise KeyError(f'category {package!r} not found')
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
        raise ValueError(f'no repo contains: {path!r}')

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
        if isinstance(obj, str):
            # check by repo id
            if obj in map(str, self.trees):
                return True

            # check by path
            path = os.path.realpath(obj)
            for repo in self.trees:
                try:
                    repo_path = os.path.realpath(repo.location)
                except AttributeError:
                    continue
                if path.startswith(repo_path):
                    return True
            return False
        elif isinstance(obj, prototype.tree):
            return obj in self.trees
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
        raise KeyError(f'package {key} not found')

    def __add__(self, other):
        if isinstance(other, prototype.tree):
            if other not in self.trees:
                self.trees += (other,)
            return self
        elif isinstance(other, tree):
            return tree(*(self.trees + other.trees))
        raise TypeError(
            "cannot add '%s' and '%s' objects"
            % (self.__class__.__name__, other.__class__.__name__))

    def __radd__(self, other):
        if isinstance(other, prototype.tree):
            if other not in self.trees:
                self.trees = (other,) + self.trees
            return self
        elif isinstance(other, tree):
            return tree(*(other.trees + self.trees))
        raise TypeError(
            "cannot add '%s' and '%s' objects"
            % (other.__class__.__name__, self.__class__.__name__))

    def __repr__(self):
        return '<%s.%s trees=%r @%#8x>' % (
            self.__class__.__module__, self.__class__.__name__,
            getattr(self, 'trees', 'unset'),
            id(self))

    @property
    def pkg_masks(self):
        return frozenset(chain.from_iterable(repo.pkg_masks for repo in self.trees))

    @property
    def location(self):
        return tuple(x.location for x in self.trees)

    @property
    def frozen(self):
        """bool: Repository mutability status."""
        return all(x.frozen for x in self.trees)
