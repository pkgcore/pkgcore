# Copyright: 2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

# misc things useful for tests.

from pkgcore.ebuild.ebuild_src import package
from pkgcore.ebuild.cpv import CPV
from pkgcore.ebuild.atom import atom
from pkgcore.repository.util import SimpleTree
from pkgcore.ebuild.misc import collapsed_restrict_to_data
from pkgcore.restrictions.packages import AlwaysTrue

default_arches = set(["x86", "ppc", "amd64", "ia64"])

class FakePkg(package):
    def __init__(self, cpvstr, data=None, shared=None, repo=None):
        if data is None:
            data = {}

        for x in ("DEPEND", "RDEPEND", "PDEPEND", "IUSE", "LICENSE"):
            data.setdefault(x, "")
        
        cpv = CPV(cpvstr)
        package.__init__(self, shared, repo, cpv.category, cpv.package,
            cpv.fullver)
        object.__setattr__(self, "data", data)


class Options(dict):
    __setattr__ = dict.__setitem__
    __getattr__ = dict.__getitem__
    __delattr__ = dict.__delitem__


class FakeProfile(object):

    def __init__(self, masked_use={}, forced_use={},
        provides={}, masks=[], virtuals={}, arch='x86', name='none'):
        self.provides_repo = SimpleTree(provides)
        self.masked_use = dict((atom(k), v) for k,v in masked_use.iteritems())
        self.forced_use = dict((atom(k), v) for k,v in forced_use.iteritems())
        self.masks = tuple(map(atom, masks))
        self.virtuals = SimpleTree(virtuals)
        self.arch = arch
        self.name = name

        self.forced_data = collapsed_restrict_to_data(
            [(AlwaysTrue, (self.arch,))],
            self.forced_use.iteritems())

        self.masked_data = collapsed_restrict_to_data(
            [(AlwaysTrue, default_arches)],
            self.masked_use.iteritems())
            
    def make_virtuals_repo(self, repo):
        return self.virtuals
