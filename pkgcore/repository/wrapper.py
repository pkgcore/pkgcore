# Copyright: 2006-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
simple repository wrapping to override the package instances returned
"""

# icky.
# ~harring
from pkgcore.repository import prototype, errors
from snakeoil.klass import GetAttrProxy
from itertools import imap

class tree(prototype.tree):

    """wrap an existing repository yielding wrapped packages."""

    def __init__(self, repo, package_class):
        """
        @param repo: L{pkgcore.repository.prototype.tree} instance to wrap
        @param package_class: callable to yield the package instance
        """
        self.raw_repo = repo
        if not isinstance(self.raw_repo, prototype.tree):
            raise errors.InitializationError(
                "%s is not a repository tree derivative" % (self.raw_repo,))
        self.package_class = package_class
        self.raw_repo = repo

    def itermatch(self, *args, **kwargs):
        return imap(self.package_class, self.raw_repo.itermatch(*args, **kwargs))

    __getattr__ = GetAttrProxy("raw_repo")

    def __len__(self):
        return len(self.raw_repo)
