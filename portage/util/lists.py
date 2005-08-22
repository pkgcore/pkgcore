# Copyright: 2005 Gentoo Foundation
# Author(s): 
# License: GPL2
# $Header$

def unique(s):
	"""lifted from python cookbook, credit: Tim Peters
	Return a list of the elements in s in arbitrary order, sans duplicates"""
	n = len(s)
	if n == 0:
		return []

	u = {}
	# assume all elements are hashable, if so, it's linear
	try:
		for x in s:
			u[x] = 1
	except TypeError:		del u
	else:						return u.keys()

	# so much for linear.  abuse sort.
	try:
		t = list(s)
		t.sort()
	except TypeError:		del t
	else:
		assert n > 0
		last = t[0]
		lasti = i = 1
		while i < n:
			if t[i] != last:
				t[lasti] = last = t[i]
				lasti += 1
			i+= 1
		return t[:lasti]

	# blah.  back to original portage.unique_array
	u = []
	for x in s:
		if x not in s:
			u.append(x)
	return u
	
def iterflatten(l):
	"""collapse [(1),2] into [1,2]"""
	iters = [iter(l)]
	while iters:
		try:
			while True:
				x = iters[-1].next()
				if isinstance(x, list) or isinstance(x, tuple):
					iters.append(iter(x))
					break
				yield x
		except StopIteration:
			iters.pop(-1)

def flatten(l):
	"""flatten, returning a list rather then an iterable"""
	return list(iterflatten(l))
