# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import operator

from pkgcore.restrictions import packages, values
from pkgcore.config import ConfigHint


class _Base(object):

    """Base for Installed and VersionedInstalled."""

    def __init__(self, vdb):
        self.vdbs = vdb

    def __iter__(self):
        restrict = packages.PackageRestriction("package_is_real",
            values.EqualityMatch(True))
        for repo in self.vdbs:
            for pkg in repo.itermatch(restrict):
                yield self.getter(pkg)


class Installed(_Base):

    """pkgset holding slotted_atoms of all installed pkgs."""

    pkgcore_config_type = ConfigHint({'vdb': 'refs:repo'}, typename='pkgset')
    getter = operator.attrgetter('slotted_atom')


class VersionedInstalled(_Base):

    """pkgset holding versioned_atoms of all installed pkgs."""

    pkgcore_config_type = ConfigHint({'vdb': 'refs:repo'}, typename='pkgset')
    getter = operator.attrgetter('versioned_atom')
