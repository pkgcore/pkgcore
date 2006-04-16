# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from collections import deque
class expandable_chain(object):
	__slot__ = ("iterables", "__weakref__")

	def __init__(self, *iterables):
		self.iterables = deque()
		self.extend(iterables)
			
	def __iter__(self):
		return self

	def next(self):
		if self.iterables is None:
			raise StopIteration
		while self.iterables:
			try:
				return self.iterables[0].next()
			except StopIteration:
				self.iterables.popleft()
		self.iterables = None
		raise StopIteration()
			

	def append(self, iterable):
		if self.iterables is None:
			raise StopIteration()
		self.iterables.append(iter(iterable))
	
	def extend(self, iterables):
		if self.iterables is None:
			raise StopIteration()
		self.iterables.extend(iter(x) for x in iterables)
	
class caching_iter(object):
	__slots__ = ("iterable", "__weakref__", "cached_list")
	
	def __init__(self, iterable):
		self.iterable = iter(iterable)
		self.cached_list = []

	def __setitem__(self, key, val):
		raise TypeError("non modifiable")

	def __getitem__(self, index):
		existing_len = len(self.cached_list)
		if index < 0:
			if self.iterable is not None:
				self.cached_list.extend(self.iterable)
				self.iterable = None
				existing_len = len(self.cached_list)

			index = existing_len + index
			if index < 0:
				raise IndexError("list index out of range")

		elif index >= existing_len - 1:
			if self.iterable is not None:
				try:
					self.cached_list.extend(self.iterable.next() 
						for x in xrange(existing_len - index + 1))
				except StopIteration:
					# consumed, baby.
					self.iterable = None
					raise IndexError("list index out of range")
		return self.cached_list[index]

	def __len__(self):
		if self.iterable is not None:
			self.cached_list.extend(self.iterable)
		return len(self.cached_list)

	def __iter__(self):
		for x in self.cached_list:
			yield x
		if self.iterable is not None:
			for x in self.iterable:
				self.cached_list.append(x)
				yield x
	
	def __str__(self):
		return "iter(%s), list: %s" % (self.iterable, str(self.cached_list))
