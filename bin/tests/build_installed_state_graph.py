#!/usr/bin/python

import sys
sys.path.insert(0, ".")

import portage.config
c = portage.config.load_config()
d = c.domain["livefs domain"]

import portage.graph.state_graph
graph = portage.graph.state_graph.StateGraph()

print "\n\n===ADDING TO GRAPH===\n"

for v in d.vdb:
	for pkg in v:
		#if str(pkg) in ["x11-terms/xterm-204", "www-client/mozilla-launcher-1.45"]:
		#	continue
		graph.add_pkg(pkg)

print "\n\n===ROOT PACKAGES===\n"

#def print_children(p, prev=[]):
#	for atom in graph.child_atoms(p):
#		for child in graph.child_pkgs(atom):
#			print (len(prev)-1)*2*" ", child
#			if child in prev:
#				continue
#			print_children(child, prev+[child])

for p in graph.root_pkgs():
	print p
	#print_children(p)


print "\n\n===UNRESOLVED===\n"
for a in graph.unresolved_atoms():
	print a, list(graph.parent_pkgs(a))
	for p in graph.pkgs:
		if a.key != p.key:
			continue
		print " *",p
		for r in a.restrictions:
			print "  ",r,"?",
			if r.match(p):
				print "Yes"
			else:
				print "No"


print "\n\n===BLOCKS===\n"
for a in graph.blocking_atoms():
	print a
	for p in graph.parent_pkgs(a):
		for c in graph.child_pkgs(a):
			if p is c:
				continue
			print "  ",p,"doesn't like",c
