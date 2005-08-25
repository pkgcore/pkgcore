# Copyright: 2005 Gentoo Foundation
# Author(s): *_curry from python cookbook, Scott David Daniels, Ben Wolfson, Nick Perkins, Alex Martelli for curry routine.
# License: GPL2
# $Id: currying.py 1911 2005-08-25 03:44:21Z ferringb $

def pre_curry(*args, **kwargs):
	"""passed in args are prefixed, with further args appended"""
	def callit(*moreargs, **morekwargs):
		kw = kwargs.copy()
		kw.update(morekwargs)
		return args[0](*(args[1:]+moreargs), **kw)
	return callit

def post_curry(*args, **kwargs):
	"""passed in args are appended to any further args supplied"""
	def callit(*moreargs, **morekwargs):
		kw = morekwargs.copy()
		kw.update(kwargs)
		return args[0](*(moreargs+args[1:]), **kw)
	return callit

