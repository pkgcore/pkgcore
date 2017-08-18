# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
repository subsystem
"""


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
