#!/bin/bash
[ -z "$1" ] && OLD="dev-util/bsdiff-4.3" || OLD="$1"
[ -z "$2" ] && NEW="${OLD}" || NEW="$2"

mkdir ~/vdb-test &> /dev/null
if [ ! -d "${HOME}/vdb-test/${OLD}" ]; then
python -c"import pkgcore.config;from pkgcore.vdb import repository;v=repository('${HOME}/vdb-test').trees[0];
v.frozen=False;
i=v.install(pkgcore.config.load_config().domain['livefs domain'].repos[0]['$OLD'].build().finalize(),
	offset='${HOME}/vdb-install');
i.finish();"
fi

echo "replacing it"

python -c"import pkgcore.config;from pkgcore.vdb import repository;v=repository('${HOME}/vdb-test').trees[0];
v.frozen=False;
i=v.replace(v['${OLD}'], pkgcore.config.load_config().domain['livefs domain'].repos[0]['${NEW}'].build().finalize(),
	offset='${HOME}/vdb-install');
i.finish();"

