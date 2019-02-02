"""Base pkgcore exceptions."""

from snakeoil.cli.exceptions import UserException


class PkgcoreException(Exception):
    """Generic pkgcore exception."""


class PkgcoreUserException(PkgcoreException, UserException):
    """Generic pkgcore exception with a sane string for non-debug, user-facing output."""


class PermissionDenied(PermissionError, PkgcoreUserException):

    def __init__(self, path, message=None, write=False):
        if message is None:
            if write:
                message = 'write access required'
            else:
                message = 'read access required'
        self.path = path
        self.message = message

    def __str__(self):
        s = f'permission denied to {self.path!r}'
        if self.message:
            s += f'; {self.message}'
        return s
