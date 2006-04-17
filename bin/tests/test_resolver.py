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
			i = args.index("--debug")
			args.pop(i)
			if len(args) == i:
				raise Exception("--debug needs to be followed by a debug level to enable")
			resolver.debug_whitelist.append(args.pop(i))
	except ValueError:
		pass

	if len(args) == 1:
		print "resolving sys-apps/portage since no atom supplied"
		atoms = [atom("sys-apps/portage")]
	else:
		atoms = [atom(x) for x in args[1:]]
	
	conf=load_config()
	domain = conf.domain["livefs domain"]
	v = domain.vdb[0]
	repo = domain.repos[0]
	r = resolver.resolver()
	da=atom("sys-apps/portage")
	map(r.add_root_atom, atoms)
	lasta = None
	for a in r.iterate_unresolved_atoms():
		resolver.debug("    unresolved atom: %s" % a)
		if a is lasta:
			import pdb;pdb.set_trace()
	
		r.satisfy_atom(a, itertools.chain(v.itermatch(a), sorted(repo.itermatch(a))))
		lasta = a
