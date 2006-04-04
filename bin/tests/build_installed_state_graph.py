#!/usr/bin/python

import sys

def load_vdb(graph, d):
	for v in d.vdb:
		for pkg in v:
			#if str(pkg) in ["x11-terms/xterm-204", "www-client/mozilla-launcher-1.45"]:
			#	continue
			graph.add_pkg(pkg)


def print_children(p, prev=[]):
	for atom in graph.child_atoms(p):
		for child in graph.child_pkgs(atom):
			print (len(prev)-1)*2*" ", child
			if child in prev:
				continue
			print_children(child, prev+[child])

def print_roots(graph):
	for p in graph.root_pkgs():
		print p
		#print_children(p)


def print_unresolved(graph):
	for a in graph.unresolved_atoms():
		print a, "[ %s ]" % ", ".join(str(x) for x in graph.parent_pkgs(a))
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

def print_blockers(graph):
	for a in graph.blocking_atoms():
		print a
		for p in graph.parent_pkgs(a):
			for c in graph.child_pkgs(a):
				if p is c:
					continue
				print "  ",p,"doesn't like",c

def gen_graph():
	import pkgcore.config
	c = pkgcore.config.load_config()
	d = c.domain["livefs domain"]

	import pkgcore.graph.state_graph
	graph = pkgcore.graph.state_graph.StateGraph()
	load_vdb(graph, d)
	return graph

if __name__ == "__main__":
	print "\n\n===ADDING TO GRAPH===\n"
	graph = gen_graph()
	print "\n\n===ROOT PACKAGES===\n"
	print_roots(graph)
	print "\n\n===UNRESOLVED===\n"
	print_unresolved(graph)
	print "\n\n===BLOCKS===\n"
	print_blockers(graph)
	if len(sys.argv) == 2:
		from pkgcore.graph.dot.util import dump_dot_file_from_graph
		dump_dot_file_from_graph(graph, sys.argv[1])
