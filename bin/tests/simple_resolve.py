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
from build_installed_state_graph import print_unresolved, print_blockers

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
		foundit = False
		l = repo.match(a)
		if l:
			x = max(l)
			print "repo match %s" % x
			sg.add_pkg(x)
		else:
			print "couldn't find repo match for atom '%s'" % a
			sys.exit(1)

changed=True
print
resolve(sg, vdb, repo)

print "\n== unresolveds =="
print_unresolved(sg)
print "\n== blockers =="
print_blockers(sg)

print
from pkgcore.util import caching
from pkgcore.restrictions import restriction
from pkgcore.package import metadata

pkg_hits = sum(v for k,v in caching.class_hits.iteritems() if issubclass(k, metadata.factory))
pkg_misses = sum(v for k,v in caching.class_misses.iteritems() if issubclass(k, metadata.factory))
rest_hits = sum(v for k,v in caching.class_hits.iteritems() if issubclass(k, restriction.base))
rest_misses = sum(v for k,v in caching.class_misses.iteritems() if issubclass(k, restriction.base))

try:
	print "debug: packages:     weakrefs: %.2f%%,  hits(%i), misses(%i)" % \
		((pkg_hits*100)/float(pkg_hits+pkg_misses), pkg_hits, pkg_misses)
except ZeroDivisionError:
	print "debug: packages:     weakrefs:   0.00%, hits(0), misses (0)"
try:
	print "debug: restrictions: weakrefs: %.2f%%, hits(%i), misses(%i)" % \
		((rest_hits*100)/float(rest_hits+rest_misses), rest_hits, rest_misses)
except ZeroDivisionError:
	print "debug: restrictions: weakrefs:   0.00%% weakref hits(0), misses (0)"
