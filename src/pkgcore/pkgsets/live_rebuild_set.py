"""A pkgset hack to provide a live-rebuild equivalent.

Note: HACK. Quick proof of concept, could do with cleaning up.
"""

from ..config.hint import ConfigHint
from ..repository.util import RepositoryGroup
from .installed import VersionedInstalled


class EclassConsumerSet(VersionedInstalled):

    pkgcore_config_type = ConfigHint(
        typename='pkgset',
        types={
            'vdb': 'refs:repo',
            'repos': 'refs:repo',
            'eclasses': 'list'},
    )

    def __init__(self, vdb, repos, eclasses):
        VersionedInstalled.__init__(self, vdb)
        self.repos = RepositoryGroup(repos)
        self.eclasses = frozenset(eclasses)

    def __iter__(self):
        for atom in VersionedInstalled.__iter__(self):
            pkgs = self.repos.match(atom)
            if not pkgs:
                # pkg is installed but no longer in any repo, just ignore it.
                continue
            assert len(pkgs) == 1, 'I do not know what I am doing: %r' % (pkgs,)
            pkg = pkgs[0]
            if self.eclasses.isdisjoint(pkg.data.get('_eclasses_', ())):
                yield atom
