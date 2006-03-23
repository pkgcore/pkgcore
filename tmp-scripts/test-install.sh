#!/bin/bash
if [ -z "$1" ]; then
	PKG="dev-util/bsdiff-4.3"
else
	PKG="$1"
fi
if [ -d ~/vdb-install/"${PKG}" ]; then
	rm -rf ~/vdb-{install,test}
fi
[ ! -d ~/vdb-install ] && mkdir ~/vdb-test
python -c"import pkgcore.config;from pkgcore.vdb import repository;v=repository('${HOME}/vdb-test').trees[0];
v.frozen=False;
p=pkgcore.config.load_config().domain['livefs domain'].repos[0]['${PKG}'];
f=p.build().finalize();
i=v.install(f,offset='${HOME}/vdb-install');
i.finish();
assert p.cpvstr in v.versions;
print v.categories;
print v.packages;
print v.versions;

"
