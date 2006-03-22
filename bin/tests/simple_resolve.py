#!/usr/bin/python
# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import sys
if len(sys.argv) == 1:
	print "need at least one arg to process for resolving"
	sys.exit(1)

from pkgcore.config import load_config  
from pkgcore.package.atom import atom
from pkgcore.graph.state_graph import StateGraph
from pkgcore.graph.simple_resolver import resolve

d=load_config().domain["livefs domain"]
sg=StateGraph()

vdb = d.vdb[0]
repo = d.repos[0]

for a in map(atom, sys.argv[1:]):
	print "querying vdb for %s" % a
	m = vdb.match(a)
	if m:
		print "found %s in vdb" % m
		map(sg.add_pkg, m)
	else:
		for x in max(repo.match(a)):
			print "repo match %s" % x
			sg.add_pkg(x)
			break
			
changed=True
print 
resolve(sg, vdb, repo)

print "== unresolveds =="
print "\n".join(sg.unresolved_atoms())
print "\n== blockers =="
print "\n".join(sg.blocking_atoms())
