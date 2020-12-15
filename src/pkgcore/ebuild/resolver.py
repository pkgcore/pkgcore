"""
resolver configuration to match portage behaviour (misbehaviour in a few spots)
"""

__all__ = ["upgrade_resolver", "min_install_resolver"]

from functools import partial
from itertools import chain

from ..repository import misc, multiplex
from ..resolver import plan
from ..restrictions import packages, values
from .atom import atom


def upgrade_resolver(vdbs, dbs, verify_vdb=True, nodeps=False,
                     force_replace=False, resolver_cls=plan.merge_plan,
                     **kwds):

    """
    generate and configure a resolver for upgrading all processed nodes.

    :param vdbs: list of :obj:`pkgcore.repository.prototype.tree` instances
        that represents the livefs
    :param dbs: list of :obj:`pkgcore.repository.prototype.tree` instances
        representing sources of pkgs
    :param verify_vdb: should we stop resolving once we hit the vdb,
        or do full resolution?
    :return: :obj:`pkgcore.resolver.plan.merge_plan` instance
    """

    f = plan.merge_plan.prefer_highest_version_strategy
    # hack.
    if nodeps:
        vdbs = list(map(misc.nodeps_repo, vdbs))
        dbs = list(map(misc.nodeps_repo, dbs))
    elif not verify_vdb:
        vdbs = list(map(misc.nodeps_repo, vdbs))
        dbs = list(dbs)

    if force_replace:
        resolver_cls = generate_replace_resolver_kls(resolver_cls)
    return resolver_cls(dbs + vdbs, plan.pkg_sort_highest, f, **kwds)


def downgrade_resolver(
        vdbs, dbs, verify_vdb=True, nodeps=False, force_replace=False,
        resolver_cls=plan.merge_plan, **kwds):
    """
    generate and configure a resolver for downgrading all processed nodes.

    :param vdbs: list of :obj:`pkgcore.repository.prototype.tree` instances
        that represents the livefs
    :param dbs: list of :obj:`pkgcore.repository.prototype.tree` instances
        representing sources of pkgs
    :param verify_vdb: should we stop resolving once we hit the vdb,
        or do full resolution?
    :return: :obj:`pkgcore.resolver.plan.merge_plan` instance
    """
    restrict = packages.OrRestriction(
        *list(atom(f'>={x.cpvstr}') for x in chain.from_iterable(vdbs)))
    f = partial(plan.merge_plan.prefer_downgrade_version_strategy, restrict)
    dbs = list(map(partial(misc.restrict_repo, restrict), dbs))
    # hack.
    if nodeps:
        vdbs = list(map(misc.nodeps_repo, vdbs))
        dbs = list(map(misc.nodeps_repo, dbs))
    elif not verify_vdb:
        vdbs = list(map(misc.nodeps_repo, vdbs))
        dbs = list(dbs)

    if force_replace:
        resolver_cls = generate_replace_resolver_kls(resolver_cls)
    return resolver_cls(dbs + vdbs, plan.pkg_sort_highest, f, **kwds)


def min_install_resolver(vdbs, dbs, verify_vdb=True, nodeps=False,
                         force_replace=False, resolver_cls=plan.merge_plan,
                         **kwds):
    """
    Resolver that tries to minimize the number of changes while installing.

    generate and configure a resolver that is focused on just
    installing requests- installs highest version it can build a
    solution for, but tries to avoid building anything not needed

    :param vdbs: list of :obj:`pkgcore.repository.prototype.tree` instances
        that represents the livefs
    :param dbs: list of :obj:`pkgcore.repository.prototype.tree` instances
        representing sources of pkgs
    :param verify_vdb: should we stop resolving once we hit the vdb,
        or do full resolution?
    :return: :obj:`pkgcore.resolver.plan.merge_plan` instance
    """

    if nodeps:
        vdbs = list(map(misc.nodeps_repo, vdbs))
        dbs = list(map(misc.nodeps_repo, dbs))
    elif not verify_vdb:
        vdbs = list(map(misc.nodeps_repo, vdbs))
        dbs = list(dbs)

    if force_replace:
        resolver_cls = generate_replace_resolver_kls(resolver_cls)
    return resolver_cls(vdbs + dbs, plan.pkg_sort_highest,
                        plan.merge_plan.prefer_reuse_strategy, **kwds)

_vdb_restrict = packages.OrRestriction(
    packages.PackageRestriction("repo.livefs", values.EqualityMatch(False)),
    packages.AndRestriction(
        packages.PackageRestriction(
            "category", values.StrExactMatch("virtual")),
        packages.PackageRestriction(
            "package_is_real", values.EqualityMatch(False)),
        ),
    )


class empty_tree_merge_plan(plan.merge_plan):

    _vdb_restriction = _vdb_restrict

    def __init__(self, dbs, *args, **kwds):
        """
        :param args: see :obj:`pkgcore.resolver.plan.merge_plan.__init__`
            for valid args
        :param kwds: see :obj:`pkgcore.resolver.plan.merge_plan.__init__`
            for valid args
        """
        super().__init__(dbs, *args, **kwds)
        # XXX *cough*, hack.
        self.default_dbs = multiplex.tree(
            *[x for x in self.all_raw_dbs if not x.livefs])


def generate_replace_resolver_kls(resolver_kls):

    class replace_resolver(resolver_kls):
        overriding_resolver_kls = resolver_kls
        _vdb_restriction = _vdb_restrict

        def add_atoms(self, restricts, **kwds):
            restricts = [packages.KeyedAndRestriction(self._vdb_restriction, x, key=x.key)
                         for x in restricts]
            return self.overriding_resolver_kls.add_atoms(self, restricts, **kwds)

    return replace_resolver
