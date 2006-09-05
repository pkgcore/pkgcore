# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
base repository template
"""

from pkgcore.util.mappings import LazyValDict
from pkgcore.util.lists import iflatten_instance
from pkgcore.package.atom import atom
from pkgcore.restrictions import values, boolean
from pkgcore.util.compatibility import any
from pkgcore.restrictions.util import collect_package_restrictions

def ix_callable(a):
    return "/".join(a)

class IterValLazyDict(LazyValDict):

    def __init__(self, key_func, val_func, override_iter=None,
                 return_func=ix_callable):
        LazyValDict.__init__(self, key_func, val_func)
        self._iter_callable = override_iter
        self.return_mangler = return_func

    def __iter__(self):
        return (
            self.return_mangler(k, ver)
            for k, v in self.iteritems() for ver in v)

    def __contains__(self, key):
        return key in iter(self)

    def __str__(self):
        return str(list(self))

    def force_regen(self, key):
        if key in self._vals:
            del self._vals[key]


class PackageIterValLazyDict(IterValLazyDict):

    def __iter__(self):
        return (k+"/"+x for k in self.iterkeys() for x in self[k])

    def __contains__(self, key):
        s = key.rsplit("/", 1)
        if len(s) != 2:
            return False
        return s[1] in self.get(s[0], ())


class CategoryIterValLazyDict(IterValLazyDict):

    def force_add(self, key):
        try:
            # force lazyvaldict to do the _keys_func work
            self[key]
        except KeyError:
            self._keys.add(key)

    def force_remove(self, key):
        try:
            # force lazyvaldict to do the _keys_func work
            self[key]
            self._keys.remove(key)
            if key in self._vals:
                del self._vals[key]
        except KeyError:
            pass

    def __iter__(self):
        return self.iterkeys()

    def __contains__(self, key):
        return key in self.keys()


class tree(object):
    """
    repository template

    @ivar raw_repo: if wrapping a repo, set raw_repo per instance to it
    @ivar livefs: boolean, set it to True if it's a repository representing a livefs
    @ivar package_class: callable to generate a package instance, must override
    @ivar configured: if a repo is unusable for merging/unmerging without being configured, set it to False
    @ivar configure: if the repository isn't configured, must be a callable yielding a configured form of the repository
    """

    raw_repo = None
    livefs = False
    package_class = None
    configured = True
    configure = None

    def __init__(self, frozen=True):
        """
        @param frozen: controls whether the repository is mutable or immutable
        """

        self.categories = CategoryIterValLazyDict(
            self._get_categories, self._get_categories)
        self.packages   = PackageIterValLazyDict(
            self.categories, self._get_packages)
        self.versions   = IterValLazyDict(
            self.packages, self._get_versions,
            return_func=lambda *t:"-".join(t))

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
        if cpv_inst.fullver not in self.versions[cpv_inst.key]:
            del cpv_inst
            raise KeyError(cpv)
        return cpv_inst

    def __setitem__(self, *values):
        raise AttributeError

    def __delitem__(self, cpv):
        raise AttributeError

    def __iter__(self):
        for cpv in self.versions:
            yield self.package_class(cpv)
        return

    def __len__(self):
        return len(self.versions)

    def match(self, atom, **kwds):
        return list(self.itermatch(atom, **kwds))

    def itermatch(self, restrict, restrict_solutions=None, sorter=None,
                  pkg_klass_override=None, force=None):

        """
        generator that yield packages that match a L{pkgcore.restrictions.packages.PackageRestriction} instance

        @param restrict: L{package restriction<pkgcore.restrictions.packages.PackageRestriction>} to search via
        @param restrict_solutions: cnf collapsed list of the restrict.  Don't play with it unless you know what you're doing
        @param sorter: callable to do sorting during searching- if sorting the results, use this instead of sorting externally
        """

        if sorter is None:
            sorter = iter

        if isinstance(restrict, atom):
            candidates = [restrict.key]
        else:
            candidates = self._identify_candidates(restrict, sorter)

        return self._internal_match(
            candidates, restrict, sorter, pkg_klass_override, force)

    def _internal_match(self, candidates, restrict, sorter,
                        pkg_klass_override, force):
        #actual matching.
        if force is None:
            match = restrict.match
        elif force:
            match = restrict.force_True
        else:
            match = restrict.force_False
        for catpkg in candidates:
            for pkg in sorter(
                self.package_class(catpkg+"-"+ver)
                for ver in self.versions.get(catpkg, [])):
                if pkg_klass_override is not None:
                    pkg = pkg_klass_override(pkg)

                if match(pkg):
                    yield pkg

    def _identify_candidates(self, restrict, sorter):
        # full expansion
        ret_mangler = self.packages.return_mangler
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
                    return self.packages
                return (
                    ret_mangler((c, p))
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
                return self.packages
            # ok. so... one doesn't specify a category, but they all
            # specify packages (or don't)
            pr = values.OrRestriction(*tuple(iflatten_instance(
                        (x[1] for x in dsolutions if x[1]), values.base)))
            return (
                ret_mangler((c, p))
                for c in sorter(self.categories)
                for p in sorter(pgetter(c, [])) if pr.match(p))

        elif any(True for x in dsolutions[1:] if bool(x[1]) != pkg_specified):
            # one (or more) don't specify pkgs, but they all specify cats.
            cr = values.OrRestriction(*tuple(iflatten_instance(
                        (x[0] for x in dsolutions), values.base)))
            cats_iter = (c for c in sorter(self.categories) if cr.match(c))
            return (
                self.packages.return_mangler((c, p))
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
                    cp = self.packages.return_mangler((c, pkg_exact.pop()))
                    if cp in self.packages:
                        return [cp]
                    return []
                cats_iter = [c]
            else:
                cat_restrict.add(values.ContainmentMatch(*cat_exact))
                cats_iter = sorter(
                    x for x in self.categories
                    if any(True for r in cat_restrict if r.match(x)))
        elif cat_restrict:
            cats_iter = sorter(
                x for x in self.categories
                if any(True for r in cat_restrict if r.match(x)))
        else:
            cats_iter = sorter(self.categories)

        if pkg_exact:
            if not pkg_restrict:
                if sorter is iter:
                    pkg_exact = tuple(pkg_exact)
                else:
                    pkg_exact = sorter(pkg_exact)
                return (
                    self.packages.return_mangler((c, p))
                    for c in cats_iter for p in pkg_exact)
            else:
                pkg_restrict.add(values.ContainmentMatch(*pkg_exact))
        
        if pkg_restrict:
            return (
                self.packages.return_mangler((c, p))
                for c in cats_iter
                for p in sorter(self.packages.get(c, []))
                if any(True for r in pkg_restrict if r.match(p)))
        elif not cat_restrict:
            if sorter is iter:
                return self.packages
            else:
                return (self.packages.return_mangler((c, p)) for c in 
                    cats_iter for p in sorter(self.packages.get(c, [])))
        return (self.packages.return_mangler((c, p))
            for c in cats_iter for p in sorter(self.packages.get(c, [])))

    def notify_remove_package(self, pkg):
        """
        internal function, notify the repository that a pkg it provides is being removed
        """
        cp = "%s/%s" % (pkg.category, pkg.package)
        self.versions.force_regen(cp)
        if len(self.versions.get(cp, [])) == 0:
            # dead package
            self.packages.force_regen(pkg.category)
            if len(self.packages.get(pkg.category, [])) == 0:
                #  dead category
                self.categories.force_remove(pkg.category)
                self.packages.force_regen(pkg.category)
            self.versions.force_regen(cp)

    def notify_add_package(self, pkg):
        """
        internal function, notify the repository that a pkg is being addeded to it
        """
        cp = "%s/%s" % (pkg.category, pkg.package)
        if pkg.category not in self.categories:
            self.categories.force_add(pkg.category)
        if cp not in self.packages:
            self.packages.force_regen(pkg.category)
        self.packages.force_regen(cp)

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
        
        @param orig: L{pkgcore.package.metadata.package} instance to install, must be from this repository instance
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
        
        @param orig: L{pkgcore.package.metadata.package} instance to install, must be from this repository instance
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
