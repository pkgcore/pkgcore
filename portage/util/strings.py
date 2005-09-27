# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: strings.py 2027 2005-09-27 06:54:18Z ferringb $

# so... this is massively slower then our little friend mister split, aparently :/
#def iter_tokens(s, splitter=" "):
#	"""iterable yielding of splitting of a string"""
#	pos = 0
#	strlen = len(s)
#	while pos < strlen:
#		if s[pos] in splitter:
#			pos+=1
#			continue
#		next_pos = pos + 1
#		try:
#			while s[next_pos] not in splitter:
#				next_pos+=1
#		except IndexError:
#			next_pos = strlen
#		yield s[pos:next_pos]
#		pos = next_pos + 1

def iter_token(s, splitter=" "):
	return iter(splitter.split(s))
