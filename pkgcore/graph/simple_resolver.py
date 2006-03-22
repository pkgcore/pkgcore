# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.graph.state_graph import StateGraph

def resolve(sg, vdb, repos, noisy=True):
	removes=[]
	changed=True
	while changed:
		changed = False
		for a in list(sg.unresolved_atoms()):
			for pkg in vdb.itermatch(a):
				if noisy:
					print "adding %s for %s" % (pkg, a)
				sg.add_pkg(pkg)
				changed = True
	
