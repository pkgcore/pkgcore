# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
compatibility module providing reimplementations of python2.5 functionality, falling back to __builtins__ if they're found
"""


if not "any" in __builtins__:
	def any(iterable):
		for x in iterable:
			if x:
				return True
		return False

if not "all" in __builtins__:
	def all(iterable):
		for x in iterable:
			if not x:
				return False
		return True
