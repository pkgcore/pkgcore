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
    "pkgcore.operations:domain@domain_ops",
    "pkgcore.repository:util@repo_utils",
    "pkgcore.ebuild:repository@ebuild_repo",
    "pkgcore.binpkg:repository@binary_repo",
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
    def source_repos(self):
        return repo_utils.RepositoryGroup(self.repos)

    @klass.jit_attr
    def source_repos_raw(self):
        repos = [x for x in self.repos_raw.itervalues()]
        return repo_utils.RepositoryGroup(repos)

    @klass.jit_attr
    def ebuild_repos(self):
        repos = [x for x in self.repos
                 if isinstance(x.raw_repo, ebuild_repo._ConfiguredTree)]
        return repo_utils.RepositoryGroup(repos)

    @klass.jit_attr
    def ebuild_repos_raw(self):
        return repo_utils.RepositoryGroup(x.raw_repo for x in self.ebuild_repos)

    @klass.jit_attr
    def binary_repos(self):
        repos = [x for x in self.repos
                 if isinstance(x.raw_repo, binary_repo.ConfiguredBinpkgTree)]
        return repo_utils.RepositoryGroup(repos)

    @klass.jit_attr
    def binary_repos_raw(self):
        return repo_utils.RepositoryGroup(x.raw_repo for x in self.binary_repos)

    @klass.jit_attr
    def installed_repos(self):
        return repo_utils.RepositoryGroup(self.vdb)

    # multiplexed repos
    all_repos = klass.alias_attr("source_repos.combined")
    all_raw_repos = klass.alias_attr("source_repos_raw.combined")
    all_ebuild_repos = klass.alias_attr("ebuild_repos.combined")
    all_raw_ebuild_repos = klass.alias_attr("ebuild_repos_raw.combined")
    all_binary_repos = klass.alias_attr("binary_repos.combined")
    all_raw_binary_repos = klass.alias_attr("binary_repos_raw.combined")
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

    def _get_tempspace(self):
        return None
