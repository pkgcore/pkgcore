"""
virtual repository, pkgs generated via callable
"""

__all__ = ("tree", "RestrictionRepo")

from snakeoil.compatibility import cmp
from snakeoil.sequences import stable_unique

from ..ebuild import atom
from ..ebuild.conditionals import DepSet
from ..package import base as pkg_base
from ..package import virtual
from ..restrictions.boolean import OrRestriction
from . import prototype


class tree(prototype.tree):

    factory_kls = staticmethod(virtual.factory)

    def __init__(self, livefs=False, frozen=False):
        """
        :param grab_virtuals_func: callable to get a package -> versions mapping
        :param livefs: is this a livefs repository?
        """
        super().__init__(frozen)
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
        if category != 'virtual':
            raise KeyError(f'no {category} category for this repository')
        self._load_data()
        return self.packages[category]


class InjectedPkg(pkg_base.wrapper):

    __slots__ = (
        "bdepend", "depend", "rdepend", "pdepend",
        "repo", "repo_id", "built", "versioned_atom", "unversioned_atom", "data",
    )
    default_bdepend = default_depend = default_rdepend = default_pdepend = DepSet()
    package_is_real = False
    is_supported = True

    def __init__(self, raw_pkg, repo, data=None):
        pkg_base.wrapper.__init__(self, raw_pkg)
        object.__setattr__(self, "repo", repo)
        object.__setattr__(self, "repo_id", repo.repo_id)
        object.__setattr__(self, "built", repo.livefs)
        object.__setattr__(self, "versioned_atom", self._raw_pkg)
        object.__setattr__(self, "unversioned_atom", self._raw_pkg.key)
        object.__setattr__(self, "bdepend", self.default_bdepend)
        object.__setattr__(self, "depend", self.default_depend)
        object.__setattr__(self, "rdepend", self.default_rdepend)
        object.__setattr__(self, "pdepend", self.default_pdepend)
        object.__setattr__(self, "data", data)

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
        if self._raw_pkg.intersects(other):
            return 0
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
        return f'injected restriction pkg: {self._raw_pkg}'

    def __repr__(self):
        return "<%s cpv=%r @%#8x>" % (self.__class__, self.cpvstr, id(self))

    def __hash__(self):
        return hash(self._raw_pkg)


class RestrictionRepo(tree):
    """Fake repo populated by packages matching a given restriction."""

    def __init__(self, repo_id, restrictions=(), frozen=False, livefs=False):
        self.repo_id = repo_id
        self._injected_pkgs = {}
        self._restrictions = {}
        for r in restrictions:
            self[r] = None
        super().__init__(livefs=livefs, frozen=frozen)

    def __setitem__(self, key, val):
        if isinstance(key, atom.atom):
            self._injected_pkgs[InjectedPkg(key, self, data=val)] = val
        else:
            self._restrictions[key] = val

    def __getitem__(self, key):
        val = self._injected_pkgs.__getitem__(key)
        if val is not None:
            return val
        return self._restrictions.__getitem__(key)

    @property
    def restriction(self):
        return OrRestriction(*self._restrictions.keys())

    def _get_categories(self, *args):
        return tuple(x.category for x in self._injected_pkgs)

    def _get_packages(self, category):
        return tuple(x.package for x in self._injected_pkgs)

    def _get_versions(self, package):
        return tuple(x.version for x in self._injected_pkgs)

    def __iter__(self):
        return iter(self._injected_pkgs)

    def itermatch(self, restrict, sorter=iter, pkg_cls=InjectedPkg):
        if isinstance(restrict, atom.atom):
            func = restrict.intersects
        else:
            func = restrict.match

        # yield any matching pkgs already injected into the repo
        for pkg in self._injected_pkgs:
            if func(pkg._raw_pkg):
                yield pkg

        # inject/yield any matching atoms into the repo that aren't blockers
        if self._restrictions and isinstance(restrict, atom.atom):
            if self.restriction.match(restrict) and not restrict.blocks:
                p = pkg_cls(restrict, self)
                self._injected_pkgs[p] = None
                yield p

    def match(self, restrict, **kwargs):
        return list(self.itermatch(restrict, **kwargs))
