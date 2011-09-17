# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2010 Marien Zwart <marien.zwart@gmail.com>
# License: BSD


"""A pkgset hack to provide a live-rebuild equivalent.

Note: HACK. Quick proof of concept, could do with cleaning up.
"""


from pkgcore.pkgsets.installed import VersionedInstalled
from pkgcore.config import ConfigHint
from snakeoil.compatibility import is_disjoint
from snakeoil.currying import partial


class EclassConsumerSet(VersionedInstalled):

    pkgcore_config_type = ConfigHint({'vdb': 'refs:repo',
                                      'portdir': 'ref:repo',
                                      'eclasses': 'list'},
                                     typename='pkgset')

    def __init__(self, vdb, portdir, eclasses):
        VersionedInstalled.__init__(self, vdb)
        self.portdir = portdir
        self.eclasses = frozenset(eclasses)

    def __iter__(self):
        matcher = partial(is_disjoint, self.eclasses)
        for atom in VersionedInstalled.__iter__(self):
            pkgs = self.portdir.match(atom)
            if not pkgs:
                # This thing is in the vdb but no longer in portdir
                # (or someone misconfigured us to use a bogus
                # portdir). Just ignore it.
                continue
            assert len(pkgs) == 1, 'I do not know what I am doing: %r' % (pkgs,)
            pkg = pkgs[0]
            if matcher(pkg.data.get('_eclasses_', ())):
                yield atom
