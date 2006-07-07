#!/usr/bin/python
import sys, os
import pkgcore.config
from pkgcore.vdb import repository;

home = os.getenv("HOME")


if len(sys.argv) >= 2:
	old = sys.argv[1]
else:
	old = "dev-util/bsdiff-4.3"

if len(sys.argv)>=3:
	new =  sys.argv[2]
else:
	new = old 

os.mkdir( home +  "/vdb-test")


if not os.path.isdir( home + "/vdb-test/" + old:
	v=repository(home + '/vdb-test').trees[0];
	v.frozen=False;
	i=v.install( pkgcore.config.load_config().domain['livefs domain'].repos[0]['$OLD'].build().finalize(), offset=home+'/vdb-install' );
	i.finish();


print "replacing it"


v=repository( home + '/vdb-test').trees[0];
v.frozen=False;
i=v.replace(v[old], pkgcore.config.load_config().domain['livefs domain'].repos[0][new].build().finalize(), offset=hone+'/vdb-install');
i.finish();"

