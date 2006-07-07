#!/usr/bin/python
import sys,os
from pkgcore.vdb import repository;

home = os.getenv("HOME")


if len(sys.argv) >= 2:
	pkg = sys.arv[1]
else:
	pkg="dev-util/bsdiff-4.3"

if not os.path.isdir(home+'/vdb-test/'+pkg):
	os.system( "./test-install.sh "  + pkg)

v=repository(home+'/vdb-test').trees[0]
v.frozen=False
p=v[pkg]
u=v.uninstall(p,offset=home+'/vdb-install')
u.finish()
assert p.cpvstr not in v.versions
print v.categories
print v.packages
print v.versions
