# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

__all__ = (
    "SimpleTree", "RepositoryGroup",
    "repo_containing_path", "get_raw_repos", "get_virtual_repos",
)

from snakeoil import klass
from snakeoil.demandload import demandload

from pkgcore.ebuild.cpv import versioned_CPV
from pkgcore.repository.prototype import tree

demandload(
    "pkgcore.repository:multiplex,virtual",
)


class SimpleTree(tree):
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
            pkg_klass = versioned_CPV
        self.livefs = livefs
        self.repo_id = repo_id
        self.package_class = pkg_klass
        tree.__init__(self, frozen=frozen)

    def _get_categories(self, *arg):
        if arg:
            return ()
        return tuple(self.cpv_dict.iterkeys())

    def _get_packages(self, category):
        return tuple(self.cpv_dict[category].iterkeys())

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
        tree.notify_remove_package(self, pkg)

    def notify_add_package(self, pkg):
        self.cpv_dict.setdefault(
            pkg.category, {}).setdefault(pkg.package, []).append(pkg.fullver)
        tree.notify_add_package(self, pkg)


class RepositoryGroup(object):
    """Group of repositories as a single unit.

    Args:
        repos (list): repo instances
        combined: combined repo, if None a multiplex repo is created
    """

    def __init__(self, repos, combined=None):
        self.repos = tuple(repos)
        if combined is None:
            if len(self.repos) == 1:
                combined = self.repos[0]
            else:
                combined = multiplex.tree(*self.repos)
        self.combined = combined

    itermatch = klass.alias_attr("combined.itermatch")
    has_match = klass.alias_attr("combined.has_match")
    match = klass.alias_attr("combined.match")
    path_restrict = klass.alias_attr("combined.path_restrict")

    def __iter__(self):
        return iter(self.repos)

    def __add__(self, other):
        if not isinstance(other, RepositoryGroup):
            raise TypeError("cannot add 'RepositoryGroup' and '%s' objects"
                            % other.__class__.__name__)
        return RepositoryGroup(self.repos + other.repos)

    def __radd__(self, other):
        if not isinstance(other, RepositoryGroup):
            raise TypeError("cannot add '%s' and 'RepositoryGroup' objects"
                            % other.__class__.__name__)
        return RepositoryGroup(other.repos + self.repos)

    @classmethod
    def change_repos(cls, repos):
        return cls(repos)


def repo_containing_path(repos, path):
    """Find the repo containing a path.

    Args:
        repos (iterable): iterable of repo objects
        path (str): path in the filesystem

    Returns:
        repo object if a matching repo is found, otherwise None.
    """
    for repo in repos:
        if path in repo:
            return repo
    return None

def get_raw_repos(repos):
    """Returns a list of raw repos found.

    repos can be either a repo instance, or a list of repos
    """
    if isinstance(repos, (list, tuple)):
        l = []
        map(l.extend, (get_raw_repos(x) for x in repos))
        return l
    while getattr(repos, "raw_repo", None) is not None:
        repos = repos.raw_repo
    if isinstance(repos, multiplex.tree):
        l = []
        map(l.extend, (get_raw_repos(x) for x in repos.trees))
        return l
    return [repos]

def get_virtual_repos(repos, sentinel=True):
    """Select only virtual repos.

    repos can be either a list of repos, or a repo to descend through.
    if sentinel is False, will select all non virtual repos
    """
    if not isinstance(repos, (tuple, list)):
        repos = get_raw_repos(repos)
    return [x for x in repos if isinstance(x, virtual.tree) == sentinel]
