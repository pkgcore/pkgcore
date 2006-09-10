#!/usr/bin/python
import sys
from pkgcore.config import load_config
from pkgcore.ebuild.atom import atom
if len(sys.argv) <= 2:
    print "need atom, phases"
    sys.exit(1)
pkg = atom(sys.argv[1])
phases = sys.argv[2:]
from pkgcore.config import load_config
p=load_config().get_default("domain").all_repos.match(pkg);
if len(p) > 1:
    print "got multiple matches to %s: %s" % (pkg, p)
    sys.exit(1)
p = p[0]
b=p.build();
phase_funcs = [getattr(b, x) for x in phases]
for phase, f in zip(phases, phase_funcs):
    print "\nexecuting phase %s" % phase
    f()
