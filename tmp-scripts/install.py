#!/usr/bin/python
import sys, os
import pkgcore.config
from pkgcore.vdb import repository;

home = os.getenv("HOME")

if len(sys.argv) >= 2:
	pkg = sys.argv[1]
else: 
	pkg = "dev-util/bsdiff-4.3"

if os.path.isdir( home + "/vdb-install/" + pkg):
	os.rmdir( home + "/vdb-install") 
	os.rmdir( home + "/vdb-test")

if not os.path.isdir( home + "/vdb-install"):
	os.mkdir( home + "/vdb-install" )
if not os.path.isdir( home  + "/vdb-test"):
	os.mkdir( home + "/vdb-test") 


v = repository( home + '/vdb-test').trees[0]
v.frozen=False
p=pkgcore.config.load_config().domain['livefs domain'].repos[0][pkg]

f=p.build().finalize()
i=v.install(f,offset= home + '/vdb-install')
i.finish()
assert p.cpvstr in v.versions
print v.categories
print v.packages
print v.versions

