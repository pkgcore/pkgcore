# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: strings.py 2029 2005-09-27 20:22:28Z ferringb $
from itertools import ifilter
# so... this is massively slower then our little friend mister split, aparently :/
def crappy_iter_tokens(s, splitter=" "):
	"""iterable yielding of splitting of a string"""
	pos = 0
	l = len(s)
	while pos < l:
		if s[pos] in splitter:
			pos += 1
			continue
		next_pos = pos + 1
		while next_pos < l and s[next_pos] not in splitter:
			next_pos+=1
		yield s[pos:next_pos]
		pos = next_pos + 1


# ya know what's sad?  This is faster for majority of cases.
# for it to be slower involves *massive* strings, and a >10 splitters.
def iter_tokens(s, splitter=" "):
	if len(splitter) > 1:
		for x in splitter[:-1]:
			s = s.replace(x, splitter[-1])
	return ifilter(None, s.split(splitter[-1]))
#	return iter(crappy_iter_tokens(s, splitter))
