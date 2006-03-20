#!/bin/bash
rm -rf ~/vdb-{install,test}
mkdir ~/vdb-test
python -c"import pkgcore.config;from pkgcore.vdb import repository;v=repository('${HOME}/vdb-test').trees[0];
v.frozen=False;
p=pkgcore.config.load_config().domain['livefs domain'].repos[0]['dev-util/bsdiff-4.3'];
f=p.build().finalize();
i=v.install(f,offset='${HOME}/vdb-install');
i.finish();
assert p.cpvstr in v.versions;
print v.categories;
print v.packages;
print v.versions;

"
