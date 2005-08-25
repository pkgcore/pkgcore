# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: strings.py 1911 2005-08-25 03:44:21Z ferringb $

def iter_tokens(s, splitter=" "):
	"""iterable yielding of splitting of a string"""
	pos = 0
	strlen = len(s)
	while pos < strlen:
		if s[pos] in splitter:
			pos+=1
			continue
		next_pos = pos + 1
		try:
			while s[next_pos] not in splitter:
				next_pos+=1
		except IndexError:
			next_pos = strlen
		yield s[pos:next_pos]
		pos = next_pos + 1

