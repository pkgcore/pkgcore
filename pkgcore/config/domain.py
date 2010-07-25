# Copyright: 2006-2009 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
base class to derive from for domain objects

Bit empty at the moment
"""
from snakeoil import klass
from snakeoil.demandload import demandload
demandload(globals(), "pkgcore.repository:multiplex",
    "pkgcore.operations:domain@domain_ops")

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
    def all_repos(self):
        """
        return a single repository representing all repositories from
        which pkgs can be installed from for this domain
        """
        if len(self.repos) == 1:
            return self.repos[0]
        return multiplex.tree(*self.repos)

    @klass.jit_attr
    def all_livefs_repos(self):
        """
        return a single repository representing all repositories representing
        what is installed for this domain.
        """
        if len(self.vdb) == 1:
            return self.vdb[0]
        return multiplex.tree(*self.vdb)

    def build_pkg(self, pkg, observer, clean=True):
        return pkg.build(self, observer=observer, clean=clean)

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
