# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: bash.py 1911 2005-08-25 03:44:21Z ferringb $

# disclaimer.  this is basically a bastardization of filter-env's approach.
# so... it's probably not perfect.
# aside from that, last I knew, char's are singletons, so iter should
# fly.

def parse(buf, var_dict={}):
	"""var_dict is passed in (or returned from this) env effectively.  must be dict"""
	
