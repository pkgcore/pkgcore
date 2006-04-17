# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from collections import deque

class expandable_chain(object):
	"""chained iterables, with the ability to add new iterables to the chain 
	as long as the instance hasn't raise StopIteration already"""

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
		"""append an iterable to the chain to be consumed"""
		if self.iterables is None:
			raise StopIteration()
		self.iterables.append(iter(iterable))
	
	def appendleft(self, iterable):
		"""prepend an iterable to in the chain"""
		if self.iterables is None:
			raise StopIteration()
		self.iterables.appendleft(iter(iterable))
	
	def extend(self, iterables):
		"""extend multiple iterable to the chain to be consumed"""
		if self.iterables is None:
			raise StopIteration()
		self.iterables.extend(iter(x) for x in iterables)

	def extendleft(self, iterables):
		"""prepend multiple iterables to the chain to be consumed"""
		if self.iterables is None:
			raise StopIteration()
		self.iterables.extendleft(iter(x) for x in iterables)


class caching_iter(object):
	"""On demand consumers from an iterable so as to appear
	like a tuple
	"""
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
				self.cached_list = tuple(self.cached_list + list(self.iterable))
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
					self.cached_list = tuple(self.cached_list)
					raise IndexError("list index out of range")
		
		return self.cached_list[index]

	def __cmp__(self, other):
		if self.iterable is not None:
			self.cached_list = tuple(self.cached_list + list(self.iterable))
			self.iterable = None
		return cmp(self.cached_list, other)
	
	def __nonzero__(self):
		if not self.cached_list:
			if self.iterable:
				try:
					self[0]
					return True
				except IndexError:
					return False
			return False
		return True
	
	def __len__(self):
		if self.iterable is not None:
			self.cached_list.extend(self.iterable)
			self.cached_list = tuple(self.cached_list)
			self.iterable = None
		return len(self.cached_list)

	def __iter__(self):
		for x in self.cached_list:
			yield x
		if self.iterable is not None:
			for x in self.iterable:
				self.cached_list.append(x)
				yield x
		else:
			return
		self.iterable = None
		self.cached_list = tuple(self.cached_list)
	
	def __hash__(self):
		if self.iterable is not None:
			self.cached_list.extend(self.iterable)
			self.cached_list = tuple(self.cached_list)
			self.iterable = None
		return hash(self.cached_list)

	def __str__(self):
		return "iter(%s), list: %s" % (self.iterable, str(self.cached_list))
