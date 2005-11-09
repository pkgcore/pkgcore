# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: __init__.py 2272 2005-11-10 00:19:01Z ferringb $

from cparser import CaseSensitiveConfigParser
import central, os
from portage.const import DEFAULT_CONF_FILE

def load_config(file=DEFAULT_CONF_FILE):
	"""the entry point for any code looking to use portagelib.
	if file exists, loads it up, else defaults to trying to load portage 2 style configs (/etc/make.conf, /etc/make.profile)

	returns the generated configuration object representing the system config.
	"""
	c = CaseSensitiveConfigParser()
	if os.path.isfile(file):
		c.read(file)
		c = central.config(c)
	else:
		# make.conf...
		raise Exception("sorry, default '%s' doesn't exist, and I don't like make.conf currently (I'm working out my issues however)" %
			file)
	return c

