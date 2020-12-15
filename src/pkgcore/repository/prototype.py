"""
base repository template
"""

__all__ = (
    "CategoryIterValLazyDict", "PackageMapping", "VersionMapping", "tree"
)

import os

from snakeoil.klass import jit_attr
from snakeoil.mappings import DictMixin, LazyValDict
from snakeoil.osutils import pjoin
from snakeoil.sequences import iflatten_instance

from ..ebuild.atom import atom
from ..operations import repo
from ..restrictions import boolean, packages, restriction, values
from ..restrictions.util import collect_package_restrictions


class IterValLazyDict(LazyValDict):

    __slots__ = ()

    def __str__(self):
        return str(list(self))

    def force_regen(self, key):
        if key in self._vals:
            del self._vals[key]
        else:
            self._keys = tuple(x for x in self._keys if x != key)


class CategoryIterValLazyDict(IterValLazyDict):

    __slots__ = ()

    def force_add(self, key):
        if key not in self:
            s = set(self._keys)
            s.add(key)
            self._keys = tuple(s)

    def force_remove(self, key):
        if key in self:
            self._keys = tuple(x for x in self._keys if x != key)

    __iter__ = IterValLazyDict.keys

    def __contains__(self, key):
        if self._keys_func is not None:
            return key in list(self.keys())
        return key in self._keys


class PackageMapping(DictMixin):

    def __init__(self, parent_mapping, pull_vals):
        self._cache = {}
        self._parent = parent_mapping
        self._pull_vals = pull_vals

    def __getitem__(self, key):
        o = self._cache.get(key)
        if o is not None:
            return o
        if key not in self._parent:
            raise KeyError(key)
        self._cache[key] = vals = self._pull_vals(key)
        return vals

    def keys(self):
        return self._parent.keys()

    def __contains__(self, key):
        return key in self._cache or key in self._parent

    def force_regen(self, cat):
        try:
            del self._cache[cat]
        except KeyError:
            pass


class VersionMapping(DictMixin):

    def __init__(self, parent_mapping, pull_vals):
        self._cache = {}
        self._parent = parent_mapping
        self._pull_vals = pull_vals

    def __getitem__(self, key):
        o = self._cache.get(key)
        if o is not None:
            return o
        if not key[1] in self._parent.get(key[0], ()):
            raise KeyError(key)
        val = self._pull_vals(key)
        self._cache[key] = val
        return val

    def keys(self):
        for cat, pkgs in self._parent.items():
            for pkg in pkgs:
                yield (cat, pkg)

    def force_regen(self, key, val):
        if val:
            self._cache[key] = val
        else:
            self._cache.pop(key, None)


class tree:
    """Template for all repository variants.

    Args:
        frozen (bool): controls whether the repository is mutable or immutable

    Attributes:
        raw_repo: if wrapping a repo, set raw_repo per instance to it
        livefs (bool): set it to True if it's a repository representing a livefs
        package_class: callable to generate a package instance, must override
        configured (bool): if a repo is unusable for merging/unmerging
            without being configured, set it to False
        configure: if the repository isn't configured, must be a callable
            yielding a configured form of the repository
        frozen_settable (bool): controls whether frozen is able to be set
            on initialization
        operations_kls: callable to generate a repo operations instance

        categories (dict): available categories in the repo
        packages (dict): mapping of packages to categories in the repo
        versions (dict): mapping of versions to packages in the repo
        frozen (bool): repository mutability status
        lock: TODO
    """

    raw_repo = None
    is_supported = True
    livefs = False
    package_class = None
    configured = True
    configure = None
    frozen_settable = True
    operations_kls = repo.operations
    pkg_masks = frozenset()

    def __init__(self, frozen=False):
        self.categories = CategoryIterValLazyDict(
            self._get_categories, self._get_categories)
        self.packages = PackageMapping(self.categories, self._get_packages)
        self.versions = VersionMapping(self.packages, self._get_versions)

        if self.frozen_settable:
            self.frozen = frozen
        self.lock = None

    def _get_categories(self, *args):
        """this must return a list, or sequence"""
        raise NotImplementedError(self, "_get_categories")

    def _get_packages(self, category):
        """this must return a list, or sequence"""
        raise NotImplementedError(self, "_get_packages")

    def _get_versions(self, package):
        """this must return a list, or sequence"""
        raise NotImplementedError(self, "_get_versions")

    def __getitem__(self, cpv):
        cpv_inst = self.package_class(*cpv)
        if cpv_inst.fullver not in self.versions[(cpv_inst.category, cpv_inst.package)]:
            raise KeyError(cpv)
        return cpv_inst

    def __setitem__(self, *vals):
        raise AttributeError

    def __delitem__(self, cpv):
        raise AttributeError

    def __iter__(self):
        """Filtered iterator over all the repo's packages.

        All packages with metadata issues are skipped.""
        """
        return self.itermatch(packages.AlwaysTrue)

    def __len__(self):
        return sum(len(v) for v in self.versions.values())

    def __contains__(self, obj):
        """Determine if a path or a package is in a repo."""
        if isinstance(obj, str):
            path = os.path.normpath(obj)
            try:
                repo_path = os.path.realpath(getattr(self, 'location'))
            except AttributeError:
                return False

            # existing relative path
            if not path.startswith(os.sep) and os.path.exists(pjoin(repo_path, path)):
                return True

            # existing full path
            fullpath = os.path.realpath(os.path.abspath(path))
            if fullpath.startswith(repo_path) and os.path.exists(fullpath):
                return True

            return False
        else:
            for pkg in self.itermatch(obj):
                return True
            return False

    def has_match(self, atom, **kwds):

        kwds.pop("sorter", None)
        kwds.pop("yield_none", None)

        for pkg in self.itermatch(atom, **kwds):
            return True
        return False

    def match(self, atom, **kwds):
        return list(self.itermatch(atom, **kwds))

    def itermatch(self, restrict, sorter=None, pkg_filter=None, versioned=True,
                  raw_pkg_cls=None, pkg_cls=None, force=None, yield_none=False):
        """Generator that yields packages match a restriction.

        :type restrict: :obj:`pkgcore.restrictions.packages.PackageRestriction`
            instance.
        :param restrict: restriction to search via
        :param sorter: callable to do sorting during searching-
            if sorting the results, use this instead of sorting externally.
        :param pkg_filter: callable to do package filtering
        :param versioned: boolean controlling returning versioned or unversioned pkgs
        :param raw_pkg_cls: custom package class to use for generating raw pkg instances
        :param pkg_cls: custom package class to override raw pkg instances with
        :param yield_none: if True then itermatch will yield None for every
            non-matching package. This is meant for use in combination with
            C{twisted.task.cooperate} or other async uses where itermatch
            should not wait many (wallclock) seconds between yielding
            packages. If you override this method you should yield
            None in long-running loops, strictly calling it for every package
            is not necessary.
        """

        if not isinstance(restrict, restriction.base):
            raise TypeError(
                f"restrict must be a pkgcore.restriction.restrictions.base instance: "
                f"got {restrict!r}")

        if sorter is None:
            sorter = iter
        if pkg_filter is None:
            pkg_filter = iter
        if raw_pkg_cls is None:
            if versioned:
                raw_pkg_cls = self.package_class
            else:
                raw_pkg_cls = lambda *args: args

        if isinstance(restrict, atom):
            candidates = [(restrict.category, restrict.package)]
        else:
            candidates = self._identify_candidates(restrict, sorter)

        if force is None:
            match = restrict.match
        elif force:
            match = restrict.force_True
        else:
            match = restrict.force_False
        return self._internal_match(
            candidates, match, raw_pkg_cls=raw_pkg_cls, pkg_cls=pkg_cls,
            yield_none=yield_none, sorter=sorter, pkg_filter=pkg_filter,
            versioned=versioned)

    def _internal_gen_candidates(self, candidates, sorter, raw_pkg_cls, pkg_filter, versioned):
        for cp in sorter(candidates):
            if versioned:
                pkgs = (raw_pkg_cls(cp[0], cp[1], ver) for ver in self.versions.get(cp, ()))
            else:
                if self.versions.get(cp, ()):
                    pkgs = (raw_pkg_cls(cp[0], cp[1]),)
                else:
                    pkgs = ()
                pkgs = iter(pkgs)
            yield from sorter(pkg_filter(pkgs))

    def _internal_match(self, candidates, match_func, pkg_cls, yield_none=False, **kwargs):
        for pkg in self._internal_gen_candidates(candidates, **kwargs):
            if pkg_cls is not None:
                pkg = pkg_cls(pkg)

            if match_func(pkg):
                yield pkg
            elif yield_none:
                yield None

    def _identify_candidates(self, restrict, sorter):
        # full expansion
        if not isinstance(restrict, boolean.base) or isinstance(restrict, atom):
            return self._fast_identify_candidates(restrict, sorter)
        dsolutions = [
            ([c.restriction
              for c in collect_package_restrictions(x, ("category",))],
             [p.restriction
              for p in collect_package_restrictions(x, ("package",))])
            for x in restrict.iter_dnf_solutions(True)]

        # see if any solution state isn't dependent on cat/pkg in anyway.
        # if so, search whole search space.
        for x in dsolutions:
            if not x[0] and not x[1]:
                if sorter is iter:
                    return self.versions
                return (
                    (c, p)
                    for c in sorter(self.categories)
                    for p in sorter(self.packages.get(c, ())))

        # simple cases first.
        # if one specifies categories, and one doesn't
        cat_specified = bool(dsolutions[0][0])
        pkg_specified = bool(dsolutions[0][1])
        pgetter = self.packages.get
        if any(True for x in dsolutions[1:] if bool(x[0]) != cat_specified):
            if any(True for x in dsolutions[1:] if bool(x[1]) != pkg_specified):
                # merde.  so we've got a mix- some specify cats, some
                # don't, some specify pkgs, some don't.
                # this may be optimizable
                return self.versions
            # ok. so... one doesn't specify a category, but they all
            # specify packages (or don't)
            pr = values.OrRestriction(
                *tuple(iflatten_instance(
                    (x[1] for x in dsolutions if x[1]), values.base)))
            return (
                (c, p)
                for c in sorter(self.categories)
                for p in sorter(pgetter(c, [])) if pr.match(p))

        elif any(True for x in dsolutions[1:] if bool(x[1]) != pkg_specified):
            # one (or more) don't specify pkgs, but they all specify cats.
            cr = values.OrRestriction(
                *tuple(iflatten_instance(
                    (x[0] for x in dsolutions), values.base)))
            cats_iter = (c for c in sorter(self.categories) if cr.match(c))
            return (
                (c, p)
                for c in cats_iter for p in sorter(pgetter(c, [])))

        return self._fast_identify_candidates(restrict, sorter)

    def _fast_identify_candidates(self, restrict, sorter):
        pkg_restrict = set()
        cat_restrict = set()
        cat_exact = set()
        pkg_exact = set()

        for x in collect_package_restrictions(restrict,
                                              ("category", "package",)):
            if x.attr == "category":
                cat_restrict.add(x.restriction)
            elif x.attr == "package":
                pkg_restrict.add(x.restriction)

        for e, s in ((pkg_exact, pkg_restrict), (cat_exact, cat_restrict)):
            l = [x for x in s
                 if isinstance(x, values.StrExactMatch) and not x.negate]
            s.difference_update(l)
            e.update(x.exact for x in l)
        del l

        if restrict.negate:
            cat_exact = pkg_exact = ()

        if cat_exact:
            if not cat_restrict and len(cat_exact) == 1:
                # Cannot use pop here, cat_exact is reused below.
                c = next(iter(cat_exact))
                if not pkg_restrict and len(pkg_exact) == 1:
                    cp = (c, pkg_exact.pop())
                    if cp in self.versions:
                        return [cp]
                    return []
                cats_iter = [c]
            else:
                cat_restrict.add(values.ContainmentMatch2(frozenset(cat_exact)))
                cats_iter = sorter(self._cat_filter(cat_restrict))
        elif cat_restrict:
            cats_iter = self._cat_filter(
                cat_restrict, negate=restrict.negate)
        else:
            cats_iter = sorter(self.categories)

        if pkg_exact:
            if not pkg_restrict:
                if sorter is iter:
                    pkg_exact = tuple(pkg_exact)
                else:
                    pkg_exact = sorter(pkg_exact)
                return (
                    (c, p)
                    for c in cats_iter for p in pkg_exact)
            else:
                pkg_restrict.add(values.ContainmentMatch2(frozenset(pkg_exact)))

        if pkg_restrict:
            return self._package_filter(
                cats_iter, pkg_restrict, negate=restrict.negate)
        elif not cat_restrict:
            if sorter is iter and not cat_exact:
                return self.versions
            else:
                return (
                    (c, p) for c in
                    cats_iter for p in sorter(self.packages.get(c, ())))
        return (
            (c, p)
            for c in cats_iter for p in sorter(self.packages.get(c, ())))

    def _cat_filter(self, cat_restricts, negate=False):
        sentinel = not negate
        cats = [x.match for x in cat_restricts]
        for x in self.categories:
            for match in cats:
                if match(x) == sentinel:
                    yield x
                    break

    def _package_filter(self, cats_iter, pkg_restricts, negate=False):
        sentinel = not negate
        restricts = [x.match for x in pkg_restricts]
        pkgs_dict = self.packages
        for cat in cats_iter:
            for pkg in pkgs_dict.get(cat, ()):
                for match in restricts:
                    if match(pkg) == sentinel:
                        yield (cat, pkg)
                        break

    def notify_remove_package(self, pkg):
        """internal function

        notify the repository that a pkg it provides is being removed
        """
        ver_key = (pkg.category, pkg.package)
        l = [x for x in self.versions[ver_key] if x != pkg.fullver]
        if not l:
            # dead package
            wipe = list(self.packages[pkg.category]) == [pkg.package]
            self.packages.force_regen(pkg.category)
            if wipe:
                self.categories.force_regen(pkg.category)
        self.versions.force_regen(ver_key, tuple(l))

    def notify_add_package(self, pkg):
        """internal function

        notify the repository that a pkg is being added to it
        """
        ver_key = (pkg.category, pkg.package)
        s = set(self.versions.get(ver_key, ()))
        s.add(pkg.fullver)
        if pkg.category not in self.categories:
            self.categories.force_add(pkg.category)
        self.packages.force_regen(pkg.category)
        self.versions.force_regen(ver_key, tuple(s))

    @property
    def operations(self):
        return self.get_operations()

    def get_operations(self, observer=None):
        return self.operations_kls(self)

    def __bool__(self):
        try:
            next(iter(self.versions))
            return True
        except StopIteration:
            return False

    def __str__(self):
        if self.aliases:
            return str(self.aliases[0])
        return repr(self)

    @property
    def aliases(self):
        potentials = (getattr(self, key, None) for key in ('repo_id', 'location'))
        return tuple(x for x in potentials if x is not None)

    @jit_attr
    def masked(self):
        """Base package mask restriction."""
        return packages.OrRestriction(*self.pkg_masks)
