# Copyright: 2005 Gentoo Foundation
# Author(s): 
# License: GPL2
# $Id: lists.py 2156 2005-10-23 23:48:48Z ferringb $

def unique(s):
	"""lifted from python cookbook, credit: Tim Peters
	Return a list of the elements in s in arbitrary order, sans duplicates"""
	n = len(s)
	# assume all elements are hashable, if so, it's linear
	try:
		return list(set(s))
	except TypeError:
		pass

	# so much for linear.  abuse sort.
	try:
		t = sorted(s)
	except TypeError:
		pass
	else:
		assert n > 0
		last = t[0]
		lasti = i = 1
		while i < n:
			if t[i] != last:
				t[lasti] = last = t[i]
				lasti += 1
			i += 1
		return t[:lasti]

	# blah.	 back to original portage.unique_array
	u = []
	for x in s:
		if x not in u:
			u.append(x)
	return u
	
def iterflatten(l):
	"""collapse [(1),2] into [1,2]"""
	iters = [iter(l)]
	while iters:
		try:
			while True:
				x = iters[-1].next()
				if hasattr(x, '__iter__') and not isinstance(x, basestring):
					iters.append(iter(x))
				else:
					yield x
		except StopIteration:
			iters.pop(-1)

			
def flatten(l):
	"""flatten, returning a list rather then an iterable"""
	return list(iterflatten(l))
