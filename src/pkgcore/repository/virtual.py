# Copyright: 2005-2008 Brian harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
virtual repository, pkgs generated via callable
"""

__all__ = ("tree", "RestrictionRepo")

from snakeoil.compatibility import cmp

from pkgcore.ebuild import atom
from pkgcore.ebuild.conditionals import DepSet
from pkgcore.package import virtual
from pkgcore.repository import prototype
from pkgcore.package import base as pkg_base


class tree(prototype.tree):

    factory_kls = staticmethod(virtual.factory)

    def __init__(self, livefs=False):
        """
        :param grab_virtuals_func: callable to get a package -> versions mapping
        :param livefs: is this a livefs repository?
        """
        super(tree, self).__init__()
        self.livefs = livefs
        vf = self.factory_kls(self)
        self.package_class = vf.new_package

    def _expand_vers(self, cp, ver):
        raise NotImplementedError(self, "_expand_vers")

    def _internal_gen_candidates(self, candidates, sorter):
        pkls = self.package_class
        for cp in candidates:
            for pkg in sorter(
                    pkls(provider, cp[0], cp[1], ver)
                    for ver in self.versions.get(cp, ())
                    for provider in self._expand_vers(cp, ver)):
                yield pkg

    def _get_categories(self, *optional_category):
        # return if optional_category is passed... cause it's not yet supported
        if optional_category:
            return ()
        return ("virtual",)

    def _load_data(self):
        raise NotImplementedError(self, "_load_data")

    def _get_packages(self, category):
        if category != "virtual":
            raise KeyError("no %s category for this repository" % category)
        self._load_data()
        return self.packages[category]


class InjectedPkg(pkg_base.wrapper):

    __slots__ = ("repo", "repo_id", "built", "depends", "rdepends", "post_rdepends")
    default_depends = default_rdepends = default_post_rdepends = DepSet()
    package_is_real = False

    def __init__(self, raw_pkg, repo):
        pkg_base.wrapper.__init__(self, raw_pkg)
        object.__setattr__(self, "repo", repo)
        object.__setattr__(self, "repo_id", repo.repo_id)
        if self.repo.livefs:
            built = True
        else:
            built = False
        object.__setattr__(self, "built", built)

        # underlying pkg deps are empty
        object.__setattr__(self, "depends", self.default_depends)
        object.__setattr__(self, "rdepends", self.default_rdepends)
        object.__setattr__(self, "post_rdepends", self.default_post_rdepends)

    @property
    def use(self):
        if self._raw_pkg.use is None:
            return ()
        return self._raw_pkg.use

    def __cmp__(self, other):
        if isinstance(other, InjectedPkg):
            other = other._raw_pkg
        elif isinstance(other, pkg_base.base):
            other = other.versioned_atom
        return cmp(self._raw_pkg, other)

    def __eq__(self, other):
        if isinstance(other, InjectedPkg):
            other = other._raw_pkg
        elif isinstance(other, pkg_base.base):
            other = other.versioned_atom
        return self._raw_pkg.intersects(other)

    def __ne__(self, other):
        if isinstance(other, InjectedPkg):
            other = other._raw_pkg
        elif isinstance(other, pkg_base.base):
            other = other.versioned_atom
        return not self._raw_pkg.intersects(other)

    def __str__(self):
        return "injected restriction pkg: %s" % (self._raw_pkg)

    def __repr__(self):
        return "injected restriction pkg: %s" % (self._raw_pkg)

    def __hash__(self):
        return hash(self._raw_pkg)


class RestrictionRepo(prototype.tree):
    """Fake repo populated by packages matching a given restriction."""

    def __init__(self, restriction, repo_id, frozen=False, livefs=False):
        self.restriction = restriction
        self._injected_pkgs = set()
        self.repo_id = repo_id
        self.frozen = frozen
        self.livefs = livefs

    def itermatch(self, restrict, sorter=iter, pkg_klass_override=InjectedPkg):
        if isinstance(restrict, atom.atom):
            # yield any matching pkgs already injected into the repo
            for pkg in self._injected_pkgs:
                if restrict.intersects(pkg._raw_pkg):
                    yield pkg

            # inject and yield any matching restrictions (atoms) into the repo that
            # aren't blockers
            if self.restriction.match(restrict) and not restrict.blocks:
                p = pkg_klass_override(restrict, self)
                self._injected_pkgs.add(p)
                yield p

    def match(self, restrict, **kwargs):
        return list(self.itermatch(restrict, **kwargs))
