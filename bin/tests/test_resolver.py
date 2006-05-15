#!/usr/bin/python

from pkgcore.config import load_config
from pkgcore.graph import linearize
from pkgcore.package.atom import atom
from pkgcore.util.lists import flatten, stable_unique


def pop_paired_args(args, arg, msg):
	rets = []
	if not isinstance(arg, (tuple, list)):
		arg = [arg]
	for a in arg:
		try:
			while True:
				i = args.index(a)
				args.pop(i)
				if len(args) == i:
					raise Exception("%s needs to be followed by an arg: %s" % (a, msg))
				rets.append(args.pop(i))
		except ValueError:
			pass
	return rets

def pop_arg(args, *arg):

	ret = False
	for a in arg:
		try:
			while True:
				args.remove(a)
				ret = True
		except ValueError:
			pass
	return ret
	

if __name__ == "__main__":
	import sys
	args = sys.argv[1:]

	if pop_arg(args, "-h", "--help"):
		print "args supported, -D, [-u|-m] and -s (system|world)"
		print "can specify additional atoms when specifying -s, no atoms/sets available, defaults to sys-apps/portage"
		sys.exit(1)

	trigger_pdb = pop_arg(args, "-p", "--pdb")
	empty_vdb = pop_arg(args, "-e", "--empty")
	upgrade = pop_arg(args, "-u", "--upgrade")
	max = pop_arg(args, "-m", "--max-upgrade")
	if max and max == upgrade:
		print "can only choose max, or upgrade"
		sys.exit(1)
	if max:
		strategy = linearize.merge_plan.force_max_version_strategy
	elif upgrade:
		strategy = linearize.merge_plan.prefer_highest_version_strategy
	else:
		strategy = linearize.merge_plan.prefer_reuse_strategy

	deep = bool(pop_arg(args, "-D", "--deep"))

	conf = load_config()

	set_targets = pop_paired_args(args, ["--set", "-s"], "pkg sets to enable")
	if set_targets:
		print "using pkgset(s): %s" % (", ".join("'%s'" % x.strip() for x in set_targets))
	set_targets = flatten([map(atom, getattr(conf, "%s_pkgset" % l)[l]) for l in set_targets], atom)
	
	if not args:
		if set_targets:
			atoms = set_targets
		else:
			print "resolving sys-apps/portage since no atom supplied"
			atoms = [atom("sys-apps/portage")]
	else:
		atoms = [atom(x) for x in args] + set_targets
	atoms = stable_unique(atoms)

	domain = conf.domain["livefs domain"]
	vdb, repo = domain.vdb[0], domain.repos[0]
	resolver = linearize.merge_plan(vdb, repo, pkg_selection_strategy=strategy, verify_vdb=deep)
	ret = True
	import time
	start_time = time.time()
	for x in atoms:
		print "\ncalling resolve for %s..." % x
		ret = resolver.add_atom(x)
		if ret:
			print "ret was",ret
			print "resolution failed"
			sys.exit(2)
	print "\nbuildplan"
	for x in resolver.state.iter_pkg_ops():
		print "%s %s" % (x[0].ljust(8), x[1])
	print "result was successfull, 'parently- took %.2f seconds" % (time.time() - start_time)
	
