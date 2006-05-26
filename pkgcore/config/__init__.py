# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os
from pkgcore.config import central, cparser, errors
from pkgcore.const import DEFAULT_CONF_FILE, GLOBAL_CONF_FILE, CONF_DEFAULTS


def load_config(local_conf_file=DEFAULT_CONF_FILE,
	global_conf_file=GLOBAL_CONF_FILE, types_file=CONF_DEFAULTS):
	"""the entry point for any code looking to use pkgcore.

	if file exists, loads it up, else defaults to trying to load
	portage 2 style configs (/etc/make.conf, /etc/make.profile)

	returns the generated configuration object representing the system config.
	"""
	types_def = cparser.configTypesFromIni(open(types_file))
	if os.path.isfile(global_conf_file) and os.path.isfile(local_conf_file):
		c = central.ConfigManager(
			[types_def],
			[cparser.configFromIni(open(local_conf_file)),
			cparser.configFromIni(open(global_conf_file)) ])
	else:
		# make.conf...
		from pkgcore.ebuild.portage_conf import configFromMakeConf
		c = central.ConfigManager([types_def], 
			[configFromMakeConf()]
			)
	return c
