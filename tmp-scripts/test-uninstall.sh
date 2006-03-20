#!/bin/bash
[ ! -d  "${HOME}/vdb-test/dev-util/bsdiff-4.3" ] && $(dirname "$0")/test-install.sh
python -c"from pkgcore.vdb import repository;
v=repository('${HOME}/vdb-test').trees[0];
v.frozen=False;
p=v['dev-util/bsdiff-4.3'];
u=v.uninstall(p,offset='${HOME}/vdb-install');
u.finish()
assert p.cpvstr not in v.versions;
print v.categories;
print v.packages;
print v.versions;"
