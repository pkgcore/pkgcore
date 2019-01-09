"""Base pkgcore exceptions."""


class PkgcoreException(Exception):
    """Generic pkgcore exception."""


class PkgcoreCliException(PkgcoreException):
    """Generic pkgcore exception with a sane string for non-debug cli output."""
