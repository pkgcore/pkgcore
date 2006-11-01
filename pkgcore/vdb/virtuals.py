# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.lists import iflatten_instance
from pkgcore.repository import virtual
from pkgcore.util.currying import partial


def _grab_virtuals(repo):
    virtuals = {}
    for pkg in repo:
        for virtualpkg in iflatten_instance(
            pkg.provides.evaluate_depset(pkg.use)):
            virtuals.setdefault(virtualpkg.package, {}).setdefault(
                pkg.fullver, []).append(pkg)

    for pkg_dict in virtuals.itervalues():
        for full_ver, rdep_atoms in pkg_dict.iteritems():
            if len(rdep_atoms) == 1:
                pkg_dict[full_ver] = rdep_atoms[0].unversioned_atom
            else:
                pkg_dict[full_ver] = packages.OrRestriction(
                    finalize=True,
                    *[x.unversioned_atom for x in rdep_atoms])
    return virtuals

def non_caching_virtuals(repo, livefs=True):
    return virtual.tree(partial(_grab_virtuals, repo), livefs=livefs)

