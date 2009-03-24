# Copyright: 2006-2009 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
base class to derive from for domain objects

Bit empty at the moment
"""
from snakeoil.demandload import demandload
demandload(globals(), "pkgcore.repository:multiplex")

# yes this is basically empty. will fill it out as the base is better
# identified.

class domain(object):

    @property
    def all_repos(self):
        """
        return a single repository representing all repositories from
        which pkgs can be installed from for this domain
        """
        all_repos = getattr(self, '_all_repos', None)
        if all_repos is None:
            if len(self.repos) == 1:
                all_repos = self.repos[0]
            else:
                all_repos = multiplex.tree(*self.repos)
            self._all_repos = all_repos
        return all_repos

    @property
    def all_livefs_repos(self):
        """
        return a single repository representing all repositories representing
        what is installed for this domain.
        """
        livefs_repos = getattr(self, '_all_livefs_repos', None)
        if livefs_repos is None:
            if len(self.vdb) == 1:
                livefs_repos = self.vdb[0]
            else:
                livefs_repos = multiplex.tree(*self.vdb)
            self._all_livefs_repos = livefs_repos
        return livefs_repos
