# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

# "More than one statement on a single line"
# pylint: disable-msg=C0321

"""
atom exceptions
"""

__all__ = ("MalformedAtom", "InvalidVersion", "InvalidCPV", "DepsetParseError")

import textwrap

from pkgcore.exceptions import PkgcoreException
from pkgcore.package import errors


class MalformedAtom(errors.InvalidDependency):

    def __init__(self, atom, err=''):
        err = ': ' + err if err else ''
        self.atom, self.err = atom, err
        super().__init__(str(self))

    def __str__(self):
        return f"invalid package atom: '{self.atom}'{self.err}"


class InvalidVersion(errors.InvalidDependency):

    def __init__(self, ver, rev, err=''):
        super().__init__(
            f"Version restriction ver='{ver}', rev='{rev}', is malformed: error {err}")
        self.ver, self.rev, self.err = ver, rev, err


class InvalidCPV(errors.InvalidPackageName):
    """Raised if an invalid cpv was passed in.

    :ivar args: single-element tuple containing the invalid string.
    :type args: C{tuple}
    """


class DepsetParseError(errors.InvalidDependency):

    def __init__(self, s, token=None, msg=None, attr=None):
        self.dep_str = s
        self.token = token
        self.msg = msg
        self.attr = attr

    def __str__(self):
        msg = []
        if self.attr is not None:
            msg.append(f'failed parsing {self.attr}')
        msg.append(f'{self.dep_str!r} is unparseable')
        if self.token is not None:
            msg.append(f'flagged token- {self.token}')
        if self.msg is not None:
            msg.append(f'{self.msg}')
        return ': '.join(msg)


class SanityCheckError(PkgcoreException):
    """Generic error for sanity check failures."""

    def verbose_msg(self):
        return str(self)

    def msg(self, verbosity, prefix='  '):
        if verbosity > 0:
            return self.verbose_msg(prefix)
        else:
            return f'{prefix}{self}'


class PkgPretendError(SanityCheckError):
    """The pkg_pretend phase check failed for a package."""

    def __init__(self, pkg, output):
        self.pkg = pkg
        self.output = output

    def __str__(self):
        return f'>>> Failed pkg_pretend: {self.pkg.cpvstr}'

    def verbose_msg(self, prefix):
        error_str = '\n'.join(f'{prefix}{line}' for line in self.output.splitlines())
        return f'{self}\n{error_str}'


class RequiredUseError(SanityCheckError):
    """REQUIRED_USE check(s) for a package failed."""

    def __init__(self, pkg, unmatched):
        self.unmatched = unmatched
        self.pkg = pkg

    def __str__(self):
        return f'>>> Failed REQUIRED_USE check: {self.pkg.cpvstr}'

    def verbose_msg(self, prefix):
        errors = []
        for node in self.unmatched:
            errors.append(textwrap.dedent(
                f"""
                Failed to match: {node}
                from: {self.pkg.required_use}
                for USE: {' '.join(self.pkg.use)}
                """
            ))
        error_str = '\n'.join(
            f'{prefix}{line}' for e in errors for line in e.strip().splitlines())
        return f'{self}\n{error_str}'
