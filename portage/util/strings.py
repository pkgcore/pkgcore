# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: strings.py 2028 2005-09-27 08:20:19Z ferringb $
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
	if len(splitter) == 1:
		return iter(s.split(splitter))
	
#	for x in range(len(splitter) -1):
#		s = splitter[x + 1].join(filter(None,s.split(splitter[x])))
#	return iter(filter(None, s.split(splitter[-1])))
	for x in range(len(splitter) -1):
		s = s.replace(splitter[x], splitter[x+1])
	return ifilter(None, s.split(splitter[-1]))
#	return iter(crappy_iter_tokens(s, splitter))
