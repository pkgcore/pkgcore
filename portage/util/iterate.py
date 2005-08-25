# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: iterate.py 1911 2005-08-25 03:44:21Z ferringb $

from itertools import islice

def enumerate(iter, start, end):
	count = start
	for r in islice(iter, start, end):
		yield count, r
		count+=1
