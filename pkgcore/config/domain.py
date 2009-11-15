# Copyright: 2006-2009 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
base class to derive from for domain objects

Bit empty at the moment
"""
from snakeoil import klass
from snakeoil.demandload import demandload
demandload(globals(), "pkgcore.repository:multiplex")

# yes this is basically empty. will fill it out as the base is better
# identified.

class domain(object):

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
