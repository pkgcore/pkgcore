# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: iterate.py 2284 2005-11-10 00:35:50Z ferringb $

from itertools import islice

def enumerate(iter, start, end):
	count = start
	for r in islice(iter, start, end):
		yield count, r
		count+=1
