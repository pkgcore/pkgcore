# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
base class to derive from for domain objects

Bit empty at the moment
"""

__all__ = ("domain",)

from snakeoil import klass
from snakeoil.demandload import demandload

demandload(
    'pkgcore.operations:domain@domain_ops',
    'pkgcore.repository.util:RepositoryGroup',
)


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
        l = [x.instantiate() for x in self._triggers]
        l.extend(self._mk_nonconfig_triggers())
        return tuple(l)

    @klass.jit_attr
    def source_repos(self):
        """Group of all repos."""
        return RepositoryGroup(self.repos)

    @klass.jit_attr
    def source_repos_raw(self):
        """Group of all repos without filtering."""
        return RepositoryGroup(self.repos_raw.itervalues())

    @klass.jit_attr
    def installed_repos(self):
        """Group of all installed repos (vdb)."""
        return RepositoryGroup(self.vdb)

    # multiplexed repos
    all_repos = klass.alias_attr("source_repos.combined")
    all_raw_repos = klass.alias_attr("source_repos_raw.combined")
    all_livefs_repos = klass.alias_attr("installed_repos.combined")

    def pkg_operations(self, pkg, observer=None):
        return pkg.operations(self, observer=observer)

    def build_pkg(self, pkg, observer, clean=True, **format_options):
        return self.pkg_operations(pkg, observer=observer).build(
            observer=observer, clean=clean, **format_options)

    def install_pkg(self, newpkg, observer):
        return domain_ops.install(self, self.all_livefs_repos, newpkg,
            observer, self.triggers, self.root)

    def uninstall_pkg(self, pkg, observer):
        return domain_ops.uninstall(self, self.all_livefs_repos, pkg, observer,
            self.triggers, self.root)

    def replace_pkg(self, oldpkg, newpkg, observer):
        return domain_ops.replace(self, self.all_livefs_repos, oldpkg, newpkg,
            observer, self.triggers, self.root)
