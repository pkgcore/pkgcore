# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
sequence related operations
"""

from pkgcore.util.iterables import expandable_chain

def unstable_unique(s):
	"""
	lifted from python cookbook, credit: Tim Peters
	Return a list of the elements in s in arbitrary order, sans duplicates
	"""

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
	"""
	return unique list from iterable, preserving ordering
	"""
	return list(iter_stable_unique(iterable))

def iter_stable_unique(iterable):
	"""
	generator yielding unique elements from iterable, preserving ordering
	"""
	s = set()
	for x in iterable:
		if x not in s:
			yield x
			s.add(x)

def iter_flatten(l, skip_flattening=(basestring,), skip_func=None):
	"""
	collapse [(1),2] into [1,2]
	
	@param skip_flattening: list of classes to not descend through
	@param skip_func: if None, skip_flattening is used- else it must be a callable 
	  that returns True when iter_flatten should escend no further
	"""
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


class ChainedLists(object):
	"""
	sequences chained together, without collapsing into a list
	"""
	__slots__ = ("_lists", "__weakref__")
	
	def __init__(self, *lists):
		"""
		all args must be sequences
		"""
		# ensure they're iterable
		for x in lists:
			iter(x)
		
		if isinstance(lists, tuple):
			lists = list(lists)
		self._lists = lists

	def __len__(self):
		return sum(len(l) for l in self._lists)

	def __getitem__(self, idx):
		if idx < 0:
			idx += len(self)
			if idx < 0:
				raise IndexError
		for l in self._lists:
			l2 = len(l)
			if idx < l2:
				return l[idx]
			idx -= l2
		else:
			raise IndexError
	
	def __setitem__(self, idx, val):
		raise TypeError("not mutable")

	def __delitem__(self, idx):
		raise TypeError("not mutable")

	def __iter__(self):
		for l in self._lists:
			for x in l:
				yield x
	
	def __contains__(self, obj):
		return obj in iter(self)

	def __str__(self):
		return "[ %s ]" % ", ".join(str(l) for l in self._lists)

	def append(self, item):
		self._lists.append(item)
	
	def extend(self, items):
		self._lists.extend(items)
