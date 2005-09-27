# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: strings.py 2031 2005-09-27 21:01:41Z ferringb $
from itertools import ifilter

def iter_tokens(s, splitter=" "):
	l = len(splitter)
	if l > 1:
		if l == 3 and "\n" in splitter and " " in splitter and "\t" in splitter:
			return iter(s.split())
		for x in splitter[:-1]:
			s = s.replace(x, splitter[-1])
	return ifilter(None, s.split(splitter[-1]))
