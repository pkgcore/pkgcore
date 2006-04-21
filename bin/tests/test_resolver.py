#!/usr/bin/python
# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import itertools
from pkgcore.graph import resolver
from pkgcore.config import load_config
from pkgcore.package.atom import atom
from pkgcore.util.lists import flatten

def pop_paired_args(args, arg, msg):
	rets = []
	try:
		while True:
			i = args.index(arg)
			args.pop(i)
			if len(args) == i:
				raise Exception("%s needs to be followed by an arg: %s" % msg)
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

	resolver.debug_whitelist.extend(pop_paired_args(args, "--debug", "debug filter to enable"))
	set_targets = pop_paired_args(args, "--set", "pkg sets to enable")

	trigger_pdb = pop_arg(args, "-p", "--pdb")
	empty_vdb = pop_arg(args, "-e", "--empty")
	
	conf=load_config()

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
	
	domain = conf.domain["livefs domain"]
	v,repo = domain.vdb[0], domain.repos[0]

	r = resolver.resolver()
	map(r.add_root_atom, reversed(atoms))

	lasta = None
	count = 0
	for a in r.iterate_unresolved_atoms():
		count += 1
		if a.blocks:
			import pdb;pdb.set_trace()
			print "caught blocker"
			
		resolver.debug("    unresolved atom: %s" % a)
		if a is lasta:
			import pdb;pdb.set_trace()
		if empty_vdb:
			r.satisfy_atom(a, sorted(repo.itermatch(a)))
		else:
			r.satisfy_atom(a, itertools.chain(v.itermatch(a), sorted(repo.itermatch(a))))
		lasta = a
		print "loop %i" % count

	if trigger_pdb:
		import pdb
		pdb.set_trace()
