#!/usr/bin/python

from pkgcore.config import load_config
from pkgcore.resolver import plan
from pkgcore.package.atom import atom
from pkgcore.util.lists import flatten, stable_unique
from pkgcore.util.repo_utils import get_raw_repos
from pkgcore.util.commandline import generate_restriction, collect_ops

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
		print "args supported, [-D || --deep], [[-u || --upgrade] | [-m || --max-upgrade]] and -s (system|world) [-d || --debug]"
		print "can specify additional atoms when specifying -s, no atoms/sets available, defaults to sys-apps/portage"
		sys.exit(1)
	if pop_arg(args, "-d", "--debug"):
		plan.limiters.add(None)
	trigger_pdb = pop_arg(args, "-p", "--pdb")
	empty_vdb = pop_arg(args, "-e", "--empty")
	upgrade = pop_arg(args, "-u", "--upgrade")
	max = pop_arg(args, "-m", "--max-upgrade")
	ignore_failures = pop_arg(args, None, "--ignore-failures")
	if max and max == upgrade:
		print "can only choose max, or upgrade"
		sys.exit(1)
	if max:
		strategy = plan.merge_plan.force_max_version_strategy
	elif upgrade:
		strategy = plan.merge_plan.prefer_highest_version_strategy
	else:
		strategy = plan.merge_plan.prefer_reuse_strategy

	deep = bool(pop_arg(args, "-D", "--deep"))

	conf = load_config()

	set_targets = pop_paired_args(args, ["--set", "-s"], "pkg sets to enable")
	if set_targets:
		print "using pkgset(s): %s" % (", ".join("'%s'" % x.strip() for x in set_targets))
	set_targets = [a for t in set_targets for a in conf.pkgset[t]]
	#map(atom, conf.pkgset[l]) for l in set_targets], restriction.base)
	
	domain = conf.domain["livefs domain"]
	vdb, repo = domain.vdb[0], domain.repos[0]
	if not args:
		if set_targets:
			atoms = set_targets
		else:
			print "resolving sys-apps/portage since no atom supplied"
			atoms = [atom("sys-apps/portage")]
	else:
		atoms = []
		for x in args:
			a = generate_restriction(x)
			if isinstance(a, atom):
				atoms.append(a)
				continue
			matches = set(pkg.key for pkg in repo.itermatch(a))
			if not matches:
				print "no matches found to %s" % x,a
				if ignore_failures:
					print "skipping %s" % x
					continue
				sys.exit(1)
			if len(matches) > 1:
				print "multiple pkg matches found for %s: %s, %s" % (x, ", ".join(sorted(matches)), a)
				if ignore_failures:
					print "skipping %s" % x
					continue
				sys.exit(2)
			# else we rebuild an atom.
			key = list(matches)[0]
			ops, text = collect_ops(x)
			if not ops:
				atoms.append(atom(key))
				continue
			atoms.append(atom(ops + key.rsplit("/", 1)[0] + "/" + text.rsplit("/",1)[-1]))
		
#		atoms = [atom(x) for x in args] + set_targets

	atoms = stable_unique(atoms)
	resolver = plan.merge_plan(vdb, repo, pkg_selection_strategy=strategy, verify_vdb=deep)
	ret = True
	failures = []
	import time
	start_time = time.time()
	for restrict in atoms:
		print "\ncalling resolve for %s..." % restrict
		ret = resolver.add_atom(restrict)
		if ret:
			print "ret was",ret
			print "resolution failed"
			failures.append(restrict)
			if not ignore_failures:
				break
	if failures:
		print "\nfailures encountered-"
		for restrict in failures:
			print "failed '%s'\npotentials-" % restrict
			match_count = 0
			for r in get_raw_repos(repo):
				l = r.match(restrict)
				if l:
					print "repo %s: [ %s ]" % (r, ", ".join(str(x) for x in l))
					match_count += len(l)
			if not match_count:
				print "no matches found in %s" % repo
			print
			if not ignore_failures:
				sys.exit(2)

	print "\nbuildplan"
	for op, pkgs in resolver.state.iter_pkg_ops():
		print "%s %s" % (op.ljust(8), ", ".join(str(y) for y in reversed(pkgs)))
	print "result was successfull, 'parently- took %.2f seconds" % (time.time() - start_time)
	
