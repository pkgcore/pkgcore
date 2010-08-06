# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
misc. repository related tools
"""

__all__ = ("get_raw_repos", "get_virtual_repos")

from pkgcore.repository import virtual

def get_raw_repos(repo):
    """
    returns a list of raw repos found.
    repo can be either a repo instance, or a list
    """
    if isinstance(repo, (list, tuple)):
        l = []
        map(l.extend, (get_raw_repos(x) for x in repo))
        return l
    while getattr(repo, "raw_repo", None) is not None:
        repo = repo.raw_repo
    if hasattr(repo, "trees"):
        l = []
        map(l.extend, (get_raw_repos(x) for x in repo.trees))
        return l
    return [repo]

def get_virtual_repos(repo, sentinel=True):
    """
    select only virtual repos
    repo can be either a list, or a repo to descend through.
    if sentinel is False, will select all non virtual repos
    """
    if not isinstance(repo, (tuple, list)):
        repo = get_raw_repos(repo)
    return [x for x in repo if isinstance(x, virtual.tree) == sentinel]
