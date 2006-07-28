# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
resolver configuration to match portage behaviour (misbehaviour in a few spots)
"""

__all__ = ["upgrade_resolver", "min_install_resolver"]

from pkgcore.resolver import plan
from pkgcore.util.iterables import caching_iter
from pkgcore.util.demandload import demandload
demandload(globals(), "pkgcore.util.repo_utils:get_virtual_repos " +
	"pkgcore.util.mappings:OrderedDict " +
	"pkgcore.repository:virtual ")


def prefer_highest_ver(resolver, dbs, atom):
	try:
		if atom.category == "virtual":
			# force vdb inspection first.
			return resolver.prefer_reuse_strategy(resolver, dbs, atom)
	except AttributeError:
		# should do inspection instead...
		pass
	return resolver.prefer_highest_version_strategy(resolver, dbs, atom)


def upgrade_resolver(vdb, dbs, verify_vdb=True, nodeps=False, force_vdb_virtuals=True, resolver_cls=plan.merge_plan, **kwds):

	"""
	generate and configure a resolver for upgrading all nodes encountered in processing
	
	@param vdb: list of L{pkgcore.repository.prototype.tree} instances that represents the livefs
	@param dbs: list of L{pkgcore.repository.prototype.tree} instances representing sources of pkgs
	@param verify_vdb: should we stop resolving once we hit the vdb, or do full resolution?
	@param force_vdb_virtuals: old style portage virtuals (non metapkgs) cannot be technically sorted since their
	versions are from multiple packages bleeding through- results make no sense essentially.  You want this option
	enabled if you're dealing in old style virtuals
	@return: L{pkgcore.resolver.plan.merge_plan} instance
	"""

	if force_vdb_virtuals:
		f = prefer_highest_ver
	else:
		f = plan.merge_plan.prefer_highest_version_strategy
	# hack.
	vdb = list(vdb.trees)
	if not isinstance(dbs, (list, tuple)):
		dbs = [dbs]
	if nodeps:
		vdb = map(plan.nodeps_repo, vdb)
		dbs = map(plan.nodeps_repo, dbs)
	elif not verify_vdb:
		vdb = map(plan.nodeps_repo, vdb)
	return resolver_cls(dbs + vdb, plan.pkg_sort_highest, f, **kwds)


def min_install_resolver(vdb, dbs, verify_vdb=True, force_vdb_virtuals=True, resolver_cls=plan.merge_plan, nodeps=False, **kwds):
	"""
	generate and configure a resolver that is focused on just installing requests- installs highest version it can build a solution for,
	but tries to avoid building anything not needed

	@param vdb: list of L{pkgcore.repository.prototype.tree} instances that represents the livefs
	@param dbs: list of L{pkgcore.repository.prototype.tree} instances representing sources of pkgs
	@param verify_vdb: should we stop resolving once we hit the vdb, or do full resolution?
	@param force_vdb_virtuals: old style portage virtuals (non metapkgs) cannot be technically sorted since their
	versions are from multiple packages bleeding through- results make no sense essentially.  You want this option
	enabled if you're dealing in old style virtuals
	@return: L{pkgcore.resolver.plan.merge_plan} instance
	"""

	# nothing fancy required for force_vdb_virtuals, we just silently ignore it.
	vdb = list(vdb.trees)
	if not isinstance(dbs, (list, tuple)):
		dbs = [dbs]
	if nodeps:
		vdb = map(plan.nodeps_repo, vdb)
		dbs = map(plan.nodeps_repo, dbs)
	elif not verify_vdb:
		vdb = map(plan.nodeps_repo, vdb)
	
	return resolver_cls(vdb + dbs, plan.pkg_sort_highest, plan.merge_plan.prefer_reuse_strategy, **kwds)


class empty_tree_merge_plan(plan.merge_plan):
	
	def __init__(self, *args, **kwds):
		"""
		@param args: see L{pkgcore.resolver.plan.merge_plan.__init__} for valid args
		@param kwds: see L{pkgcore.resolver.plan.merge_plan.__init__} for valid args
		"""
		plan.merge_plan.__init__(self, *args, **kwds)
		self.first_round_dbs = OrderedDict((repo, cache) for repo, cache in self.all_dbs.iteritems() if not repo.livefs or isinstance(repo, virtual.tree))

	def add_atom(self, atom):
		return plan.merge_plan.add_atom(self, atom, dbs=self.first_round_dbs)
