#!/bin/bash
[ ! -d  /home/bharring/vdb-test/dev-util/bsdiff-4.3 ] && $(dirname "$0")/test-install.sh
python -c'from portage.vdb import repository;
v=repository("/home/bharring/vdb-test").trees[0];
v.frozen=False;
p=v["dev-util/bsdiff-4.3"];
u=v.uninstall(p,offset="/home/bharring/vdb-install");
u.finish()'
