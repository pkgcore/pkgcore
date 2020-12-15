# "More than one statement on a single line"
# pylint: disable-msg=C0321

"""
atom exceptions
"""

__all__ = ("MalformedAtom", "InvalidVersion", "InvalidCPV", "DepsetParseError")

import textwrap

from ..exceptions import PkgcoreException
from ..package import errors


class MalformedAtom(errors.InvalidDependency):
    """Package atom doesn't follow required specifications."""

    def __init__(self, atom, err=None):
        self.atom = atom
        self.err = err
        super().__init__(str(self))

    def __str__(self):
        msg = f'invalid package atom: {self.atom!r}'
        if self.err:
            msg += f': {self.err}'
        return msg


class InvalidVersion(errors.InvalidDependency):
    """Package version doesn't follow required specifications."""

    def __init__(self, ver, rev, err=''):
        super().__init__(
            f"Version restriction ver='{ver}', rev='{rev}', is malformed: error {err}")
        self.ver, self.rev, self.err = ver, rev, err


class InvalidCPV(errors.InvalidPackageName):
    """CPV with unsupported characters or format."""


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

    def msg(self, verbosity, prefix='  '):
        if verbosity > 0:
            return self.verbose_msg(prefix)
        else:
            return f'{prefix}{self}'


class PkgPretendError(SanityCheckError):
    """The pkg_pretend phase check failed for a package."""

    def __init__(self, pkg, output, error):
        self.pkg = pkg
        self.output = output
        self.error = error

    def msg(self, verbosity=0, prefix=' '):
        header = f'>>> {self.pkg.cpvstr}: failed pkg_pretend'
        msg = []
        error_msg = self.error.msg(verbosity=verbosity)
        if verbosity > 0:
            msg.extend(self.output.splitlines())
            msg.extend(error_msg.splitlines())
            msg = [f'{prefix}{l}' for l in msg]
        elif error_msg:
            header += f': {error_msg}'
        return '\n'.join([header] + msg)


class RequiredUseError(SanityCheckError):
    """REQUIRED_USE check(s) for a package failed."""

    def __init__(self, pkg, unmatched):
        self.pkg = pkg
        self.unmatched = unmatched

    def msg(self, verbosity=0, prefix='  '):
        header = f'>>> {self.pkg.cpvstr}: failed REQUIRED_USE'
        errors = []
        for node in self.unmatched:
            errors.append(textwrap.dedent(
                f"""
                Failed to match: {node}
                from: {self.pkg.required_use}
                for USE: {' '.join(sorted(self.pkg.use))}
                """
            ))
        msg = [f'{prefix}{line}' for e in errors for line in e.strip().splitlines()]
        return '\n'.join([header] + msg)
