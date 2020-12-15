"""
simple repository wrapping to override the package instances returned
"""

__all__ = ("tree",)

# icky.
# ~harring

from snakeoil.klass import DirProxy, GetAttrProxy

from ..operations import repo
from . import errors, prototype


class tree(prototype.tree):
    """Repository wrapper binding configuration data to contained packages."""

    operation_kls = repo.operations_proxy

    def __init__(self, repo, package_class):
        """
        :param repo: :obj:`pkgcore.repository.prototype.tree` instance to wrap
        :param package_class: callable to yield the package instance
        """
        self.raw_repo = repo
        if not isinstance(self.raw_repo, prototype.tree):
            raise errors.InitializationError(
                f'{self.raw_repo!r} is not a repository tree derivative')
        self.package_class = package_class
        self.raw_repo = repo

    def itermatch(self, *args, **kwargs):
        return map(self.package_class, self.raw_repo.itermatch(*args, **kwargs))

    __getattr__ = GetAttrProxy("raw_repo")
    __dir__ = DirProxy("raw_repo")

    def __len__(self):
        return len(self.raw_repo)
