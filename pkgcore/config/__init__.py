# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2


import os

from pkgcore.config import central, cparser, errors
from pkgcore.const import DEFAULT_CONF_FILE, CONF_DEFAULTS


def load_config(conf_file=DEFAULT_CONF_FILE, types_file=CONF_DEFAULTS):
	"""the entry point for any code looking to use pkgcore.

	if file exists, loads it up, else defaults to trying to load
	portage 2 style configs (/etc/make.conf, /etc/make.profile)

	returns the generated configuration object representing the system config.
	"""
	if os.path.isfile(conf_file):
		c = central.ConfigManager(
			[cparser.configTypesFromIni(open(types_file))],
			[cparser.configFromIni(open(conf_file))])
	else:
		# make.conf...
		raise errors.BaseException(
			"sorry, config file '%s' doesn't exist, and I don't like "
			"make.conf currently (I'm working out my issues however)" %
			conf_file)
	return c
