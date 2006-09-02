# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
configuration subsystem
"""

# keep these imports as minimal as possible; access to pkgcore.config.introspect isn't uncommon, thus don't trigger till actually needed
from pkgcore.const import CONF_DEFAULTS, GLOBAL_CONF_FILE, SYSTEM_CONF_FILE, USER_CONF_FILE


def load_config(user_conf_file=USER_CONF_FILE,
				system_conf_file=SYSTEM_CONF_FILE,
				global_conf_file=GLOBAL_CONF_FILE,
				types_file=CONF_DEFAULTS):
	"""
	the main entry point for any code looking to use pkgcore.

	@param user_conf_file: file to attempt to load, else defaults to trying to load
	portage 2 style configs (/etc/make.conf, /etc/make.profile)

	@return: L{pkgcore.config.central.ConfigManager} instance representing the system config.
	"""

	from pkgcore.config import central, cparser, errors
	import os

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
