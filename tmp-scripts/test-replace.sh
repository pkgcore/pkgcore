#!/bin/bash
mkdir ~/vdb-test &> /dev/null
if [ ! -d ${HOME}/vdb-test/dev-util/bsdiff-4.3 ]; then
python -c"import pkgcore.config;from pkgcore.vdb import repository;v=repository('${HOME}/vdb-test').trees[0];
v.frozen=False;
i=v.install(pkgcore.config.load_config().domain['livefs domain'].repos[0]['dev-util/bsdiff-4.3'].build().finalize(),
	offset='${HOME}/vdb-install');
i.finish();"
fi

echo "replacing it"

python -c"import pkgcore.config;from pkgcore.vdb import repository;v=repository('${HOME}/vdb-test').trees[0];
v.frozen=False;
i=v.replace(v['dev-util/bsdiff-4.3'], pkgcore.config.load_config().domain['livefs domain'].repos[0]['dev-util/bsdiff-4.3'].build().finalize(),
	offset='${HOME}/vdb-install');
i.finish();"

