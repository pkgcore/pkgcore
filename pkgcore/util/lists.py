# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.iterables import expandable_chain

def unstable_unique(s):
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

def stable_unique(iterable):
	return list(iter_stable_unique(iterable))

def iter_stable_unique(iterable):
	s = set()
	for x in iterable:
		if x not in s:
			yield x
			s.add(x)

def iter_flatten(l, skip_flattening=(basestring,), skip_func=None):
	"""collapse [(1),2] into [1,2]"""
	if skip_func is None:
		func = lambda x:isinstance(x, skip_flattening)
	else:
		func = skip_func

	if func(l):
		yield l
		return
	iters = expandable_chain(l)
	try:
		while True:
			x = iters.next()
			if hasattr(x, '__iter__') and not func(x):
				iters.appendleft(x)
			else:
				yield x
	except StopIteration:
		pass

def flatten(l, skip_flattening=(basestring,)):
	"""flatten, returning a list rather then an iterable"""
	return list(iter_flatten(l, skip_flattening=skip_flattening))
