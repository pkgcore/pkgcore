#!/usr/bin/env python

import pkgcore.config
import pkgcore.ebuild.atom
import pkgcore.ebuild.ebd

c = pkgcore.config.load_config(location='/etc/portage')
d = c.get_default('domain')
r = d.installed_repos[0]
pkg = r.match(pkgcore.ebuild.atom.atom('app-misc/hello'))[0]

op = pkgcore.ebuild.ebd.misc_operations(d, pkg)
ret = op._generic_phase('uptodate', True, True)
print(ret)

import IPython
IPython.embed()
