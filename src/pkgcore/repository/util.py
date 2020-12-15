__all__ = (
    "SimpleTree", "RepositoryGroup",
    "get_raw_repos", "get_virtual_repos",
)

from snakeoil import klass
from snakeoil.mappings import DictMixin

from ..ebuild.cpv import VersionedCPV
from . import multiplex, prototype, virtual


class SimpleTree(prototype.tree):
    """Fake, in-memory repository.

    Args:
        cpv_dict (dict): CPVs to populate the repo with
        pkg_klass: class of packages in repo
        livefs (bool): regular repo if False, vdb if True
        frozen (bool): repo is modifiable if False, otherwise readonly
        repo_id (str): repo ID
    """

    def __init__(self, cpv_dict, pkg_klass=None, livefs=False, frozen=True,
                 repo_id=None):
        self.cpv_dict = cpv_dict
        if pkg_klass is None:
            pkg_klass = VersionedCPV
        self.livefs = livefs
        self.repo_id = repo_id
        self.package_class = pkg_klass
        super().__init__(frozen=frozen)

    def _get_categories(self, *arg):
        if arg:
            return ()
        return tuple(self.cpv_dict.keys())

    def _get_packages(self, category):
        return tuple(self.cpv_dict[category].keys())

    def _get_versions(self, cp_key):
        return tuple(self.cpv_dict[cp_key[0]][cp_key[1]])

    def notify_remove_package(self, pkg):
        vers = self.cpv_dict[pkg.category][pkg.package]
        vers = [x for x in vers if x != pkg.fullver]
        if vers:
            self.cpv_dict[pkg.category][pkg.package] = vers
        else:
            del self.cpv_dict[pkg.category][pkg.package]
            if not self.cpv_dict[pkg.category]:
                del self.cpv_dict[pkg.category]
        super().notify_remove_package(pkg)

    def notify_add_package(self, pkg):
        self.cpv_dict.setdefault(
            pkg.category, {}).setdefault(pkg.package, []).append(pkg.fullver)
        super().notify_add_package(pkg)


class RepositoryGroup(DictMixin):
    """Group of repos as a single unit.

    Args:
        repos (iterable): repo instances
        combined: combined repo, if None a multiplex repo is created
    """

    __externally_mutable__ = False

    def __init__(self, repos=(), combined=None):
        self.repos = tuple(repos)
        if combined is None:
            combined = multiplex.tree(*self.repos)
        self.combined = combined

    itermatch = klass.alias_attr("combined.itermatch")
    has_match = klass.alias_attr("combined.has_match")
    match = klass.alias_attr("combined.match")
    path_restrict = klass.alias_attr("combined.path_restrict")

    def __contains__(self, key):
        return key in self.combined

    def __iter__(self):
        return iter(self.repos)

    def __getitem__(self, key):
        if isinstance(key, str):
            func = lambda x: key in x.aliases
        elif isinstance(key, int):
            return self.repos[key]
        else:
            func = lambda x: key == x
        try:
            return next(filter(func, self.repos))
        except StopIteration:
            raise KeyError(key)

    def keys(self):
        return (r.repo_id for r in self.repos)

    def items(self):
        return ((r.repo_id, r) for r in self.repos)

    def values(self):
        return iter(self.repos)

    def __add__(self, other):
        if isinstance(other, prototype.tree):
            if other not in self.repos:
                self.repos += (other,)
                self.combined += other
            return self
        elif isinstance(other, RepositoryGroup):
            return RepositoryGroup(self.repos + other.repos)
        elif isinstance(other, (list, tuple)):
            return RepositoryGroup(self.repos + tuple(other))
        raise TypeError(
            "cannot add '%s' and '%s' objects"
            % (self.__class__.__name__, other.__class__.__name__))

    def __radd__(self, other):
        if isinstance(other, prototype.tree):
            if other not in self.repos:
                self.repos = (other,) + self.repos
                self.combined = other + self.combined
            return self
        elif isinstance(other, RepositoryGroup):
            return RepositoryGroup(other.repos + self.repos)
        elif isinstance(other, (list, tuple)):
            return RepositoryGroup(tuple(other) + self.repos)
        raise TypeError(
            "cannot add '%s' and '%s' objects"
            % (other.__class__.__name__, self.__class__.__name__))

    @classmethod
    def change_repos(cls, repos):
        return cls(repos)

    @property
    def real(self):
        return RepositoryGroup(get_virtual_repos(self, False))

    @property
    def virtual(self):
        return RepositoryGroup(get_virtual_repos(self))

    def repo_match(self, path):
        """Find the repo containing a path.

        Args:
            path (str): path in the filesystem

        Returns:
            repo object if a matching repo is found, otherwise None.
        """
        for repo in self.repos:
            if path in repo:
                return repo
        return None


def get_raw_repos(repos):
    """Returns a list of raw repos found.

    repos can be either a repo instance, or a list of repos
    """
    if isinstance(repos, (RepositoryGroup, list, tuple)):
        l = []
        for x in repos:
            l.extend(get_raw_repos(x))
        return l
    while getattr(repos, "raw_repo", None) is not None:
        repos = repos.raw_repo
    if isinstance(repos, multiplex.tree):
        l = []
        for x in repos.trees:
            l.extend(get_raw_repos(x))
        return l
    return [repos]


def get_virtual_repos(repos, sentinel=True):
    """Select only virtual repos.

    repos can be either a list of repos, or a repo to descend through.
    if sentinel is False, will select all non virtual repos
    """
    if not isinstance(repos, (RepositoryGroup, list, tuple)):
        repos = get_raw_repos(repos)
    return [x for x in repos if isinstance(x, (virtual.tree, SimpleTree)) == sentinel]
