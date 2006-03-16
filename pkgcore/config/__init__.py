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
	if os.path.isfile(global_conf_file) and os.path.isfile(local_conf_file):
		c = central.ConfigManager(
			[cparser.configTypesFromIni(open(types_file))],
			[cparser.configFromIni(open(local_conf_file)),
			cparser.configFromIni(open(global_conf_file)) ])
	else:
		# make.conf...
		raise errors.BaseException("sorry, config file %r or %r doesn't exist,"
			" and I don't like make.conf currently (I'm working out my "
			" issues however)" % (local_conf_file, global_conf_file))
	return c
