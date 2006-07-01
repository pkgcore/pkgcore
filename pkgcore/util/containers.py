# Copyright: 2005-2006 Brian Harring <ferringb@gmail.com>
# License: GPL2
# $Id:$


"""
collection of container classes
"""

class InvertedContains(set):

	"""Set that inverts all contains lookups results

	mainly useful in conjuection with LimitedChangeSet for converting from blacklist to whitelist
	
	Not able to be iterated over also
	"""

	def __contains__(self, key):
		return not set.__contains__(self, key)

	def __iter__(self):
		# infinite set, non iterable.
		raise TypeError


class LimitedChangeSet(object):

	"""Set used to limit the number of times a key can be removed/added

	specifically deleting/adding a key only once per commit,
	optionally blocking changes to certain keys.
	"""

	_removed	= 0
	_added		= 1

	def __init__(self, initial_keys, unchangable_keys=None):
		self._new = set(initial_keys)
		if unchangable_keys is None:
			self.__blacklist = []
		else:
			if isinstance(unchangable_keys, (list, tuple)):
				unchangable_keys = set(unchangable_keys)
			self.__blacklist = unchangable_keys
		self.__changed = set()
		self.__change_order = []
		self.__orig = frozenset(self._new)

	def add(self, key):
		if key in self.__changed or key in self.__blacklist:
			# it's been del'd already once upon a time.
			raise Unchangable(key)

		self._new.add(key)
		self.__changed.add(key)
		self.__change_order.append((self._added, key))

	def remove(self, key):
		if key in self.__changed or key in self.__blacklist:
			raise Unchangable(key)

		if key in self._new:
			self._new.remove(key)
		self.__changed.add(key)
		self.__change_order.append((self._removed, key))

	def __contains__(self, key):
		return key in self._new

	def changes_count(self):
		return len(self.__change_order)

	def commit(self):
		self.__orig = frozenset(self._new)
		self.__changed.clear()
		self.__change_order = []

	def rollback(self, point=0):
		l = self.changes_count()
		if point < 0 or point > l:
			raise TypeError("%s point must be >=0 and <= changes_count()" % point)
		while l > point:
			change, key = self.__change_order.pop(-1)
			self.__changed.remove(key)
			if change == self._removed:
				self._new.add(key)
			else:
				self._new.remove(key)
			l -= 1

	def __str__(self):
		return str(self._new).replace("set(", "LimitedChangeSet(", 1)

	def __iter__(self):
		return iter(self._new)

	def __len__(self):
		return len(self._new)

	def __eq__(self, other):
		if isinstance(other, LimitedChangeSet):
			return self._new == other._new
		elif isinstance(other, set):
			return self._new == other
		return False


class Unchangable(Exception):

	def __init__(self, key):
		self.key = key

	def __str__(self):
		return "key '%s' is unchangable" % self.key


class ProtectedSet(object):

	"""
	basic container duck typing, wraps a set pushing all changes into a secondary set

	be aware that it lacks majority of set methods
	"""
	def __init__(self, orig_set):
		self._orig = orig_set
		self._new = set()
	
	def __contains__(self, key):
		return key in self._orig or key in self._new
	
	def __len__(self):
		return len(self._orig.union(self._new))

	def add(self, key):
		if key not in self._orig:
			self._new.add(key)
