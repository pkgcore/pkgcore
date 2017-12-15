# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
base class to derive from for domain objects

Bit empty at the moment
"""

__all__ = ("MissingFile", "Failure", "domain")

from itertools import chain

from snakeoil import klass
from snakeoil.demandload import demandload

from pkgcore.config.errors import BaseError

demandload(
    'pkgcore.operations:domain@domain_ops',
    'pkgcore.repository.util:RepositoryGroup',
)


class MissingFile(BaseError):
    """Required file is missing."""
    def __init__(self, filename, setting):
        BaseError.__init__(
            self, "setting %s points at %s, which doesn't exist."
            % (setting, filename))
        self.file, self.setting = filename, setting


class Failure(BaseError):
    """Generic domain failure."""
    def __init__(self, text):
        BaseError.__init__(self, "domain failure: %s" % (text,))
        self.text = text


# yes this is basically empty. will fill it out as the base is better
# identified.
class domain(object):

    fetcher = None
    tmpdir = None
    _triggers = ()

    def _mk_nonconfig_triggers(self):
        return ()

    @property
    def triggers(self):
        config_triggers = (x.instantiate() for x in self._triggers)
        return tuple(chain(config_triggers, self._mk_nonconfig_triggers()))

    def pkg_operations(self, pkg, observer=None):
        domain = self.get_package_domain(pkg)
        return pkg.operations(domain, observer=observer)

    def build_pkg(self, pkg, observer, failed=False, clean=True, **format_options):
        domain = self.get_package_domain(pkg)
        return domain.pkg_operations(pkg, observer=observer).build(
            observer=observer, failed=failed, clean=clean, **format_options)

    def install_pkg(self, newpkg, observer):
        domain = self.get_package_domain(newpkg)
        return domain_ops.install(
            domain, domain.all_installed_repos, newpkg, observer, domain.root)

    def uninstall_pkg(self, pkg, observer):
        domain = self.get_package_domain(pkg)
        return domain_ops.uninstall(
            domain, domain.all_installed_repos, pkg, observer, domain.root)

    def replace_pkg(self, oldpkg, newpkg, observer):
        domain = self.get_package_domain(newpkg)
        return domain_ops.replace(
            domain, domain.all_installed_repos, oldpkg, newpkg, observer, domain.root)
