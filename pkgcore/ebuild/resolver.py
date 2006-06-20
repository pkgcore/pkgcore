# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.resolver import plan
from pkgcore.util.iterables import caching_iter

def prefer_highest_ver(resolver, vdb, dbs, atom):
	try:
		if atom.category == "virtual":
			# force vdb inspection first.
			return caching_iter(x for r in [vdb] + dbs for x in r.itermatch(atom, sorter=plan.pkg_sort_highest))
	except AttributeError:
		# should do inspection instead...
		pass
	return plan.merge_plan.prefer_highest_version_strategy(resolver, vdb, dbs, atom)

def upgrade_resolver(vdb, dbs, verify_vdb=True, force_vdb_virtuals=True):
	if force_vdb_virtuals:
		f = prefer_highest_ver
	else:
		f = plan.merge_plan.prefer_highest_version
	if not verify_vdb:
		vdb = plan.nodeps_repo(vdb)

	return plan.merge_plan(vdb, dbs, f)

def min_install_resolver(vdb, dbs, verify_vdb=True, force_vdb_virtuals=True):
	# nothing fancy required for force_vdb_virtuals, we just silently ignore it.
	if not verify_vdb:
		vdb = plan.nodeps_repo(vdb)
	
	return plan.merge_plan(vdb, dbs, plan.merge_plan.prefer_reuse_strategy)
