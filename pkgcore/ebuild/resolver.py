# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.resolver import plan
from pkgcore.util.iterables import caching_iter
from pkgcore.util.repo_utils import get_virtual_repos

def prefer_highest_ver(resolver, dbs, atom):
	try:
		if atom.category == "virtual":
			# force vdb inspection first.
			return resolver.prefer_reuse_strategy(resolver, dbs, atom)
	except AttributeError:
		# should do inspection instead...
		pass
	return resolver.prefer_highest_version_strategy(resolver, dbs, atom)

def upgrade_resolver(vdb, dbs, verify_vdb=True, force_vdb_virtuals=True):
	if force_vdb_virtuals:
		f = prefer_highest_ver
	else:
		f = plan.merge_plan.prefer_highest_version_strategy
	# hack.
	vdb = list(vdb.trees)
	if not verify_vdb:
		vdb = plan.nodeps_repo(vdb)
	if not isinstance(dbs, (list, tuple)):
		dbs = [dbs]
	return plan.merge_plan(dbs + vdb, plan.pkg_sort_highest, f)

def min_install_resolver(vdb, dbs, verify_vdb=True, force_vdb_virtuals=True):
	# nothing fancy required for force_vdb_virtuals, we just silently ignore it.
	vdb = list(vdb.trees)
	if not verify_vdb:
		vdb = plan.nodeps_repo(vdb)
	if not isinstance(dbs, (list, tuple)):
		dbs = [dbs]
	
	return plan.merge_plan(vdb + dbs, plan.pkg_sort_highest, plan.merge_plan.prefer_reuse_strategy)
