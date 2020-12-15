"""
base class to derive from for domain objects

Bit empty at the moment
"""

__all__ = ("MissingFile", "Failure", "domain")

from ..exceptions import PkgcoreException
from ..operations import domain as domain_ops


class MissingFile(PkgcoreException):
    """Required file is missing."""

    def __init__(self, filename, setting):
        super().__init__(
            f"setting {setting} points at {filename!r}, which doesn't exist.")
        self.file, self.setting = filename, setting


class Failure(PkgcoreException):
    """Generic domain failure."""

    def __init__(self, text):
        super().__init__(f'domain failure: {text}')
        self.text = text


# yes this is basically empty. will fill it out as the base is better
# identified.
class domain:

    fetcher = None
    tmpdir = None
    _triggers = ()

    @property
    def triggers(self):
        return tuple(self._triggers)

    def pkg_operations(self, pkg, observer=None):
        domain = self.get_package_domain(pkg)
        return pkg.operations(domain, observer=observer)

    def build_pkg(self, pkg, observer=None, failed=False, clean=True, **kwargs):
        domain = self.get_package_domain(pkg)
        return domain.pkg_operations(pkg, observer=observer).build(
            observer=observer, failed=failed, clean=clean, **kwargs)

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
