# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: inheritance.py 2284 2005-11-10 00:35:50Z ferringb $

def check_for_base(obj, allowed):
	"""Look through __class__ to see if any of the allowed classes are found, returning the first allowed found"""
	for x in allowed:
		if issubclass(obj.__class__, x):
			return x
	return None
