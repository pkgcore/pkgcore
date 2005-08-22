# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

from ConfigParser import ConfigParser

class CaseSensitiveConfigParser(ConfigParser):
	def optionxform(self, val):
		return val
