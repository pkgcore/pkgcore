"""Base pkgcore exceptions."""

from snakeoil.cli.exceptions import CliException


class PkgcoreException(Exception):
    """Generic pkgcore exception."""


class PkgcoreCliException(PkgcoreException, CliException):
    """Generic pkgcore exception with a sane string for non-debug cli output."""
