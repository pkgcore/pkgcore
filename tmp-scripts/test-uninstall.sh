#!/bin/bash
if [ -z "$1" ]; then
	PKG="dev-util/bsdiff-4.3"
else
	PKG="$1"
fi
[ ! -d  "${HOME}/vdb-test/$kg" ] && $(dirname "$0")/test-install.sh
python -c"from pkgcore.vdb import repository;
v=repository('${HOME}/vdb-test').trees[0];
v.frozen=False;
p=v['${PKG}'];
u=v.uninstall(p,offset='${HOME}/vdb-install');
u.finish()
assert p.cpvstr not in v.versions;
print v.categories;
print v.packages;
print v.versions;"
