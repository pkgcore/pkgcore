#!/usr/bin/python

import portage
from portage_dep import *
from portage_syntax import *

vdb = portage.db["/"]["vartree"].dbapi

preferred = []
allcp = vdb.cp_all()
for cp in allcp:
	preferred.append(Atom(cp))

preferred = prepare_prefdict(preferred)

tgraph = StateGraph()

allatoms = []
for atomstr in portage.settings.packages:
	if atomstr[0] == "*":
		allatoms.append(Atom(atomstr[1:]))

for atomstr in portage.grabfile("/var/lib/portage/world"):
	allatoms.append(Atom(atomstr))

rdeps = DependSpec(element_class=Atom)
rdeps.elements = allatoms
dummypkg = GluePkg("sets/world-1.0", "set", "0", [], DependSpec(), rdeps)
rdeps = transform_virtuals(dummypkg, rdeps, portage.settings.virtuals)
rdeps = transform_dependspec(rdeps, preferred)
rdeps.compact()
dummypkg = GluePkg("sets/world-1.0", "set", "0", [], DependSpec(), rdeps)
tgraph.add_package(dummypkg, True)

def create_pkg(cpv):
	aux = vdb.aux_get(cpv, ["SLOT","USE","RDEPEND","PDEPEND"])
	slot = aux[0]
	use = aux[1].split()
	rdeps = DependSpec(aux[2] + " " + aux[3], Atom)
	rdeps.resolve_conditions(use)
	pkg = GluePkg(cpv, "installed", slot, use, DependSpec(), rdeps)
	rdeps = transform_virtuals(pkg, rdeps, portage.settings.virtuals)
	rdeps = transform_dependspec(rdeps, preferred)
	pkg = GluePkg(cpv, "installed", slot, use, DependSpec(), rdeps)
	return pkg

while True:
	changed = False
	for atom in tgraph.get_unmatched_atoms():
		matches = vdb.match(str(atom))
		if matches:
			tgraph.add_package(create_pkg(portage.best(matches)))
			changed = True
	if changed:
		continue
	for atom in tgraph.get_unmatched_preferentials():
		matches = vdb.match(str(atom))
		if matches:
			tgraph.add_package(create_pkg(portage.best(matches)))
			changed = True
			break
	if changed:
		continue
	if tgraph.get_conflicts():
		conflict = pkg.get_conflicts()[0]
		print "Conflict:",conflict
		cpvs = []
		for pkg in conflict:
			cpvs.append(str(pkg))
		cpvs.remove(portage.best(cpvs))
		for pkg in conflict:
			if str(pkg) in cpvs:
				tgraph.remove(pkg)
		changed = True
	if changed:
		continue
	if tgraph.get_unneeded_packages():
		pkg = tgraph.get_unneeded_packages()[0]
		print "Unneeded:",pkg
		tgraph.remove_package(pkg)
		changed = True
	if not changed:
		break

allcpv = []
for cp in allcpv:
	allcpv.extend(vdb.match(cp))

neededcpv = []
for pkg in tgraph.get_needed_packages():
	neededcpv.append(str(pkg))

for cpv in allcpv:
	if cpv not in neededcpv:
		print "No runtime deps on",cpv
