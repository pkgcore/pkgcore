__all__ = ("Installed", "VersionedInstalled")

import operator

from ..config.hint import ConfigHint
from ..restrictions import packages, values


class _Base:
    """Base for Installed and VersionedInstalled."""

    def __init__(self, vdb):
        self.vdbs = vdb

    def __iter__(self):
        restrict = packages.PackageRestriction(
            "package_is_real", values.EqualityMatch(True))
        for repo in self.vdbs:
            for pkg in repo.itermatch(restrict):
                yield self.getter(pkg)


class Installed(_Base):
    """Set of packages holding slotted atoms of all installed packages."""
    pkgcore_config_type = ConfigHint({'vdb': 'refs:repo'}, typename='pkgset')
    getter = operator.attrgetter('slotted_atom')


class VersionedInstalled(_Base):
    """Set of packages holding versioned atoms of all installed packages."""
    pkgcore_config_type = ConfigHint({'vdb': 'refs:repo'}, typename='pkgset')
    getter = operator.attrgetter('versioned_atom')
