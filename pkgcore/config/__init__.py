# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os
from pkgcore.config import central, cparser, errors
from pkgcore.const import (
	CONF_DEFAULTS, GLOBAL_CONF_FILE, SYSTEM_CONF_FILE, USER_CONF_FILE)


def load_config(user_conf_file=USER_CONF_FILE,
				system_conf_file=SYSTEM_CONF_FILE,
				global_conf_file=GLOBAL_CONF_FILE,
				types_file=CONF_DEFAULTS):
	"""the entry point for any code looking to use pkgcore.

	if file exists, loads it up, else defaults to trying to load
	portage 2 style configs (/etc/make.conf, /etc/make.profile)

	returns the generated configuration object representing the system config.
	"""
	types_def = cparser.configTypesFromIni(open(types_file))
	have_system_conf = os.path.isfile(system_conf_file)
	have_user_conf = os.path.isfile(user_conf_file)
	if have_system_conf or have_user_conf:
		configs = []
		if have_user_conf:
			configs.append(cparser.configFromIni(open(user_conf_file)))
		if have_system_conf:
			configs.append(cparser.configFromIni(open(system_conf_file)))
		configs.append(cparser.configFromIni(open(global_conf_file)))
		c = central.ConfigManager([types_def], configs)
	else:
		# make.conf...
		from pkgcore.ebuild.portage_conf import configFromMakeConf
		c = central.ConfigManager([types_def], 
			[configFromMakeConf()]
			)
	return c
