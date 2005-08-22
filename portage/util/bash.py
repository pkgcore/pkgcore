# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

# disclaimer.  this is basically a bastardization of filter-env's approach.
# so... it's probably not perfect.
# aside from that, last I knew, char's are singletons, so iter should
# fly.

def parse(buf, var_dict={}):
	"""var_dict is passed in (or returned from this) env effectively.  must be dict"""
	
