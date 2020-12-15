"""
exceptions thrown by repository classes.

Need to extend the usage a bit further still.
"""

from ..exceptions import PkgcoreException, PkgcoreUserException


class RepoError(PkgcoreException):
    """General repository error."""

    def __init__(self, msg):
        self.msg = msg


class InitializationError(RepoError, PkgcoreUserException):
    """General repository initialization failure."""

    def __str__(self):
        return f"repo init failed: {self.msg}"


class InvalidRepo(InitializationError, PkgcoreUserException):
    """Repository is not a repo or is otherwise invalid."""

    def __str__(self):
        return f"invalid repo: {self.msg}"


class UnsupportedRepo(RepoError, PkgcoreUserException):
    """Repository uses an unknown EAPI or is otherwise not supported."""

    def __init__(self, repo):
        self.repo = repo

    def __str__(self):
        return (
            f'{self.repo.repo_id!r} repo: '
            f'unsupported repo EAPI {str(self.repo.eapi)!r}'
        )
