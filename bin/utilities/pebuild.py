#!/usr/bin/python
import sys
if len(sys.argv) <= 2:
	print "need atom, phases"
	sys.exit(1)
pkg = sys.argv[1]
phases = sys.argv[2:]
from pkgcore.config import load_config
p=load_config().domain['livefs domain'].repos[0][pkg];
b=p.build();
phase_funcs = [getattr(b, x) for x in phases]
for phase, f in zip(phases, phase_funcs):
	print "\nexecuting phase %s" % phase
	f()
