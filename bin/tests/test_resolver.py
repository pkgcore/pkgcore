#!/usr/bin/python
# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import itertools
from pkgcore.graph import resolver
from pkgcore.config import load_config
from pkgcore.package.atom import atom

if __name__ == "__main__":
	import sys
	args = sys.argv[1:]

	try:
		while True:
			args.remove("--debug")
			i = args.index("--debug")
			args.pop(i)
			if len(args) == i:
				raise Exception("--debug needs to be followed by a debug level to enable")
			resolver.debug_whitelist.append(args.pop(i))
	except ValueError:
		pass

	trigger_pdb = [x for x in args if x not in ("-p", "--pdb")]
	trigger_pdb, args = args != trigger_pdb, trigger_pdb
			
	if not args:
		print "resolving sys-apps/portage since no atom supplied"
		atoms = [atom("sys-apps/portage")]
	else:
		atoms = [atom(x) for x in args]
	
	conf=load_config()
	domain = conf.domain["livefs domain"]
	v,repo = domain.vdb[0], domain.repos[0]

	r = resolver.resolver()
	map(r.add_root_atom, atoms)

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
		r.satisfy_atom(a, itertools.chain(v.itermatch(a), sorted(repo.itermatch(a))))
		lasta = a
		print "loop %i" % count

	if trigger_pdb:
		import pdb
		pdb.set_trace()
