# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
base repository template
"""

from pkgcore.util.mappings import LazyValDict, DictMixin
from pkgcore.util.lists import iflatten_instance
from pkgcore.ebuild.atom import atom
from pkgcore.restrictions import values, boolean, restriction
from pkgcore.util.compatibility import any
from pkgcore.restrictions.util import collect_package_restrictions


class IterValLazyDict(LazyValDict):

    def __init__(self, key_func, val_func, override_iter=None):
        LazyValDict.__init__(self, key_func, val_func)
        self._iter_callable = override_iter

    def __str__(self):
        return str(list(self))

    def force_regen(self, key):
        if key in self._vals:
            del self._vals[key]
        else:
            self._keys = tuple(x for x in self._keys if x != key)

class CategoryIterValLazyDict(IterValLazyDict):

    def force_add(self, key):
        try:
            # force lazyvaldict to do the _keys_func work
            self[key]
        except KeyError:
            s = set(self._keys)
            s.add(key)
            self._keys = tuple(s)

    def force_remove(self, key):
        try:
            # force lazyvaldict to do the _keys_func work
            self[key]
            if key in self:
                self._keys = tuple(x for x in self._keys if x != key)
        except KeyError:
            pass
    
    def __iter__(self):
        return self.iterkeys()

    def __contains__(self, key):
        # suck.
        return key in self.keys()


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

    def iterkeys(self):
        return self._parent.iterkeys()
    
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
        self._known_keys = {}
        self._finalized = False

    def __getitem__(self, key):
        o = self._cache.get(key)
        if o is not None:
            return o
        cat, pkg = key
        known_pkgs = self._known_keys.get(cat)
        if known_pkgs is None:
            if self._finalized:
                raise KeyError(key)
            self._known_keys[cat] = known_pkgs = set(self._parent[cat])
        if pkg not in known_pkgs:
            raise KeyError(key)

        val = self._pull_vals(key)
        self._cache[key] = val
        known_pkgs.remove(pkg)
        return val

    def iterkeys(self):
        for key in self._cache:
            yield key

        if not self._finalized:
            for cat, pkgs in self._parent.iteritems():
                if cat in self._known_keys:
                    continue
                s = set()
                for pkg in pkgs:
                    if (cat, pkg) in self._cache:
                        continue
                    s.add(pkg)
                self._known_keys[cat] = s
            self._finalized = True

        for cat, pkgs in self._known_keys.iteritems():
            for pkg in list(pkgs):
                yield cat, pkg

    def __contains__(self, key):
        try:
            self[key]
            return True
        except KeyError:
            return False            

    def force_regen(self, key, val):
        if val:
            self._cache[key] = val
        else:
            self._cache.pop(key, None)
            self._known_keys.pop(key[0], None)


class tree(object):
    """
    repository template

    @ivar raw_repo: if wrapping a repo, set raw_repo per instance to it
    @ivar livefs: boolean, set it to True if it's a repository representing
        a livefs
    @ivar package_class: callable to generate a package instance, must override
    @ivar configured: if a repo is unusable for merging/unmerging
        without being configured, set it to False
    @ivar configure: if the repository isn't configured, must be a callable
        yielding a configured form of the repository
    """

    raw_repo = None
    livefs = False
    package_class = None
    configured = True
    configure = None
    syncable = False

    def _mangle_version_keys(self, packages=None):
        if packages:
            p = packages.iteritems()
        else:
            p = self.packages.iteritems()
        for c, v in p:
            for p in v:
                yield c,p

    def __init__(self, frozen=True):
        """
        @param frozen: controls whether the repository is mutable or immutable
        """

        self.categories = CategoryIterValLazyDict(
            self._get_categories, self._get_categories)
        self.packages   = PackageMapping(self.categories,
            self._get_packages)
        self.versions = VersionMapping(self.packages, self._get_versions)

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
        cpv_inst = self.package_class(cpv)
        if cpv_inst.fullver not in self.versions[(cpv.category, cpv.package)]:
            del cpv_inst
            raise KeyError(cpv)
        return cpv_inst

    def __setitem__(self, *vals):
        raise AttributeError

    def __delitem__(self, cpv):
        raise AttributeError

    def __iter__(self):
        for cp, t in self.versions.iteritems():
            for v in t:
                yield self.package_class(cp[0], cp[1], v)
        return

    def __len__(self):
        return sum(len(v) for v in self.versions.itervalues())

    def match(self, atom, **kwds):
        return list(self.itermatch(atom, **kwds))

    def itermatch(self, restrict, restrict_solutions=None, sorter=None,
                  pkg_klass_override=None, force=None, yield_none=False):

        """
        generator that yields packages match a restriction.

        @type restrict : L{pkgcore.restrictions.packages.PackageRestriction}
            instance
        @param restrict: restriction to search via
        @param restrict_solutions: cnf collapsed list of the restrict.
            Don't play with it unless you know what you're doing
        @param sorter: callable to do sorting during searching-
            if sorting the results, use this instead of sorting externally.
        @param yield_none: if True then itermatch will yield None for every
            non-matching package. This is meant for use in combination with
            C{twisted.task.cooperate} or other async uses where itermatch
            should not wait many (wallclock) seconds between yielding
            packages. If you override this method you should yield
            None in long-running loops, strictly calling it for every package
            is not necessary.
        """

        if not isinstance(restrict, restriction.base):
            raise TypeError("restrict must be a "
                "pkgcore.restriction.restrictions.base instance: "
                "got %r" % restrict)

        if sorter is None:
            sorter = iter

        if isinstance(restrict, atom):
            candidates = [(restrict.category, restrict.package)]
        else:
            candidates = self._identify_candidates(restrict, sorter)

        return self._internal_match(
            candidates, restrict, sorter, pkg_klass_override, force,
            yield_none=yield_none)

    def _internal_match(self, candidates, restrict, sorter,
                        pkg_klass_override, force, yield_none=False):
        #actual matching.
        if force is None:
            match = restrict.match
        elif force:
            match = restrict.force_True
        else:
            match = restrict.force_False
        for catpkg in candidates:
            for pkg in sorter(self.package_class(catpkg[0], catpkg[1], ver)
                for ver in self.versions.get(catpkg, [])):
                if pkg_klass_override is not None:
                    pkg = pkg_klass_override(pkg)

                if match(pkg):
                    yield pkg
                elif yield_none:
                    yield None

    def _identify_candidates(self, restrict, sorter):
        # full expansion

        if not isinstance(restrict, boolean.base) or isinstance(restrict, atom):
            return self._fast_identify_candidates(restrict, sorter)
        dsolutions = [
            ([c.restriction
              for c in collect_package_restrictions(x, ["category"])],
             [p.restriction
              for p in collect_package_restrictions(x, ["package"])])
            for x in restrict.iter_dnf_solutions(True)]

        for x in dsolutions:
            if not x[0] and not x[1]:
                # great... one doesn't rely on cat/pkg.
                if iter is sorter:
                    return self.versions
                return (
                    (c,p)
                    for c in sorter(self.categories)
                    for p in sorter(self.packages.get(c, [])))
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
            pr = values.OrRestriction(*tuple(iflatten_instance(
                        (x[1] for x in dsolutions if x[1]), values.base)))
            return ((c,p)
                for c in sorter(self.categories)
                for p in sorter(pgetter(c, [])) if pr.match(p))

        elif any(True for x in dsolutions[1:] if bool(x[1]) != pkg_specified):
            # one (or more) don't specify pkgs, but they all specify cats.
            cr = values.OrRestriction(*tuple(iflatten_instance(
                        (x[0] for x in dsolutions), values.base)))
            cats_iter = (c for c in sorter(self.categories) if cr.match(c))
            return ((c, p)
                for c in cats_iter for p in sorter(pgetter(c, [])))

        return self._fast_identify_candidates(restrict, sorter)

    def _fast_identify_candidates(self, restrict, sorter):
        pkg_restrict = set()
        cat_restrict = set()
        cat_exact = set()
        pkg_exact = set()

        for x in collect_package_restrictions(restrict,
                                              ["category", "package"]):
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

        if cat_exact:
            if not cat_restrict and len(cat_exact) == 1:
                c = cat_exact.pop()
                if not pkg_restrict and len(pkg_exact) == 1:
                    cp = (c, pkg_exact.pop())
                    if cp in self.versions:
                        return [cp]
                    return []
                cats_iter = [c]
            else:
                cat_restrict.add(values.ContainmentMatch(*cat_exact))
                cats_iter = sorter(self._cat_filter(cat_restrict))
        elif cat_restrict:
            cats_iter = self._cat_filter(cat_restrict)
        else:
            cats_iter = sorter(self.categories)

        if pkg_exact:
            if not pkg_restrict:
                if sorter is iter:
                    pkg_exact = tuple(pkg_exact)
                else:
                    pkg_exact = sorter(pkg_exact)
                return (
                    (c,p)
                    for c in cats_iter for p in pkg_exact)
            else:
                pkg_restrict.add(values.ContainmentMatch(*pkg_exact))

        if pkg_restrict:
            return self._package_filter(cats_iter, pkg_restrict)
        elif not cat_restrict:
            if sorter is iter:
                return self.versions
            else:
                return ((c,p) for c in
                    cats_iter for p in sorter(self.packages.get(c, [])))
        return ((c,p)
            for c in cats_iter for p in sorter(self.packages.get(c, [])))

    def _cat_filter(self, cat_restricts):
        cats = [x.match for x in cat_restricts]
        for x in self.categories:
            for match in cats:
                if match(x):
                    yield x
                    break

    def _package_filter(self, cats_iter, pkg_restricts):
        restricts = [x.match for x in pkg_restricts]
        pkgs_dict = self.packages
        for cat in cats_iter:
            for pkg in pkgs_dict.get(cat, ()):
                for match in restricts:
                    if match(pkg):
                        yield (cat, pkg)
                        break

    def notify_remove_package(self, pkg):
        """
        internal function,

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
        """
        internal function,

        notify the repository that a pkg is being addeded to it
        """
        ver_key = (pkg.category, pkg.package)
        s = set(self.versions.get(ver_key, []))
        s.add(pkg.fullver)
        if pkg.category not in self.categories:
            self.categories.force_add(pkg.category)
        self.packages.force_regen(pkg.category)
        self.versions.force_regen(ver_key, tuple(s))

    def install(self, pkg, *a, **kw):
        """
        internal function, install a pkg to the repository

        @param pkg: L{pkgcore.package.metadata.package} instance to install
        @param a: passed to _install
        @param kw: passed to _install
        @raise AttributeError: if the repository is frozen (immutable)
        @return: L{pkgcore.interfaces.repo.install} instance
        """
        if self.frozen:
            raise AttributeError("repo is frozen")
        return self._install(pkg, *a, **kw)

    def _install(self, pkg, *a, **kw):
        """
        internal install function- must be overrided in derivatives

        @param pkg: L{pkgcore.package.metadata.package} instance to install
        @param a: passed to _install
        @param kw: passed to _install
        @return: L{pkgcore.interfaces.repo.install} instance
        """
        raise NotImplementedError(self, "_install")

    def uninstall(self, pkg, *a, **kw):
        """
        internal function, uninstall a pkg from the repository

        @param pkg: L{pkgcore.package.metadata.package} instance to install
        @param a: passed to _install
        @param kw: passed to _install
        @raise AttributeError: if the repository is frozen (immutable)
        @return: L{pkgcore.interfaces.repo.install} instance
        """
        if self.frozen:
            raise AttributeError("repo is frozen")
        return self._uninstall(pkg, *a, **kw)

    def _uninstall(self, pkg, *a, **kw):
        """
        internal uninstall function- must be overrided in derivatives

        @param pkg: L{pkgcore.package.metadata.package} instance to install
        @param a: passed to _install
        @param kw: passed to _install
        @return: L{pkgcore.interfaces.repo.install} instance
        """
        raise NotImplementedError(self, "_uninstall")

    def replace(self, orig, new, *a, **kw):
        """
        internal function, replace a pkg in the repository with another

        @param orig: L{pkgcore.package.metadata.package} instance to install,
            must be from this repository instance
        @param new: L{pkgcore.package.metadata.package} instance to install
        @param a: passed to _install
        @param kw: passed to _install
        @raise AttributeError: if the repository is frozen (immutable)
        @return: L{pkgcore.interfaces.repo.install} instance
        """
        if self.frozen:
            raise AttributeError("repo is frozen")
        return self._replace(orig, new, *a, **kw)

    def _replace(self, orig, new, *a, **kw):
        """
        internal replace function- must be overrided in derivatives

        @param orig: L{pkgcore.package.metadata.package} instance to install,
            must be from this repository instance
        @param new: L{pkgcore.package.metadata.package} instance to install
        @param a: passed to _install
        @param kw: passed to _install
        @return: L{pkgcore.interfaces.repo.install} instance
        """
        raise NotImplementedError(self, "_replace")

    def __nonzero__(self):
        try:
            iter(self.versions).next()
            return True
        except StopIteration:
            return False
