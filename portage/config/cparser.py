# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: cparser.py 2272 2005-11-10 00:19:01Z ferringb $

from ConfigParser import ConfigParser

class CaseSensitiveConfigParser(ConfigParser):
	def optionxform(self, val):
		return val
