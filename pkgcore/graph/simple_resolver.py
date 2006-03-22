# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.graph.state_graph import StateGraph

def resolve(sg, vdb, repos, noisy=True):
	removes=[]
	changed=True
	while changed:
		changed = False
		for a in list(sg.unresolved_atoms()):
			vdb_matched=False
			for pkg in vdb.itermatch(a):
				if noisy:
					print "adding %s for %s from vdb" % (pkg, a)
				sg.add_pkg(pkg)
				changed = True
				vdb_matched=True
			if not vdb_matched:
				l = repos.match(a)
				if l:
					pkg = max(l)
					if noisy:
						print "adding %s for %s from repo" % (pkg, a)
					sg.add_pkg(pkg)
					changed = True
				else:
					print "caught unresolvable node %s" % a
			
