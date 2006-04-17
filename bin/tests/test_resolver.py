#!/usr/bin/python
import itertools
from pkgcore.graph.resolver import resolver, debug
from pkgcore.config import load_config
from pkgcore.package.atom import atom

if __name__ == "__main__":
	import sys
	if len(sys.argv) == 1:
		print "resolving sys-apps/portage since no atom supplied"
		atoms = [atom("sys-apps/portage")]
	else:
		atoms = [atom(x) for x in sys.argv[1:]]
	
	conf=load_config()
	domain = conf.domain["livefs domain"]
	v = domain.vdb[0]
	repo = domain.repos[0]
	r = resolver()
	da=atom("sys-apps/portage")
	map(r.add_root_atom, atoms)
	lasta = None
	for a in r.iterate_unresolved_atoms():
		debug("    unresolved atom: %s" % a)
		if a is lasta:
			import pdb;pdb.set_trace()
	
		r.satisfy_atom(a, itertools.chain(v.itermatch(a), sorted(repo.itermatch(a))))
		lasta = a
