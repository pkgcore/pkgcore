# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
base class to derive from for domain objects

Bit empty at the moment
"""

__all__ = ("domain",)

from snakeoil import klass
from snakeoil.demandload import demandload
demandload(globals(),
    "pkgcore.repository:multiplex,util@repo_utils",
    "pkgcore.operations:domain@domain_ops",

)

# yes this is basically empty. will fill it out as the base is better
# identified.

class domain(object):

    fetcher = None
    _triggers = ()

    def _mk_nonconfig_triggers(self):
        return ()

    @property
    def triggers(self):
        l = [x.instantiate() for x in self._triggers]
        l.extend(self._mk_nonconfig_triggers())
        return tuple(l)

    @klass.jit_attr
    def source_repositories(self):
        return repo_utils.RepositoryGroup(self.repos)

    @klass.jit_attr
    def installed_repositories(self):
        return repo_utils.RepositoryGroup(self.vdb)

    all_repos = klass.alias_attr("source_repositories.combined")
    all_livefs_repos = klass.alias_attr("installed_repositories.combined")

    def get_pkg_operations(self, pkg, observer=None):
        return pkg.operations(self, observer=observer)

    def build_pkg(self, pkg, observer, clean=True):
        return self.get_pkg_operations(pkg, observer=observer).build(observer=observer, clean=clean)

    def install_pkg(self, newpkg, observer):
        return domain_ops.install(self, self.all_livefs_repos, newpkg,
            observer, self.triggers, self.root)

    def uninstall_pkg(self, pkg, observer):
        return domain_ops.uninstall(self, self.all_livefs_repos, pkg, observer,
            self.triggers, self.root)

    def replace_pkg(self, oldpkg, newpkg, observer):
        return domain_ops.replace(self, self.all_livefs_repos, oldpkg, newpkg,
            observer, self.triggers, self.root)

    def _get_tempspace(self):
        return None
