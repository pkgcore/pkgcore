# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
WARNING, module may not be around long term (limited functionality)

provides iter_tokens, basically an overload split() that functions the same regardless of the splitter
"""

from itertools import ifilter


def iter_tokens(s, splitter=" "):
	l = len(splitter)
	if l > 1:
		if l == 3 and "\n" in splitter and " " in splitter and "\t" in splitter:
			return iter(s.split())
		for x in splitter[:-1]:
			s = s.replace(x, splitter[-1])
	return ifilter(None, s.split(splitter[-1]))
