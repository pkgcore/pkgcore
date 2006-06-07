# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from itertools import imap, chain, ifilterfalse
from pkgcore.util.currying import alias_class_method
import UserDict


class LazyValDict(UserDict.DictMixin):

	"""Mapping that loads values via a callable

	given a function to get keys, and to look up the val for those keys, it'll
	lazy load key definitions, and values as requested
	"""

	def __init__(self, get_keys_func, get_val_func):
		"""
		get_keys_func is a callable that is JIT called with no args	 returns a tuple of keys, or supports __contains__
		get_val_func is a callable that is JIT called with the key requested
		"""
		if not callable(get_val_func):
			raise TypeError("get_val_func isn't a callable")
		if hasattr(get_keys_func, "__iter__"):
			self._keys = get_keys_func
			self._keys_func = None
		else:
			if not callable(get_keys_func):
				raise TypeError("get_keys_func isn't iterable nor is it callable")
			self._keys_func = get_keys_func
		self._val_func = get_val_func
		self._vals = {}

	def __setitem__(self, key, value):
		raise AttributeError

	def __delitem__(self, key):
		raise AttributeError

	def __getitem__(self, key):
		if self._keys_func is not None:
			self._keys = set(self._keys_func())
			self._keys_func = None
		if key in self._vals:
			return self._vals[key]
		if key in self._keys:
			v = self._vals[key] = self._val_func(key)
			return v
		raise KeyError(key)

	def keys(self):
		if self._keys_func is not None:
			self._keys = set(self._keys_func())
			self._keys_func = None
		return list(self._keys)

	def iterkeys(self):
		if self._keys_func is not None:
			self._keys = set(self._keys_func())
			self._keys_func = None
		return iter(self._keys)

	def itervalues(self):
		return imap(self.__getitem__, self.iterkeys())

	def iteritems(self):
		return ((k, self[k]) for k in self.iterkeys())

	def __contains__(self, key):
		if self._keys_func is not None:
			self._keys = set(self._keys_func())
			self._keys_func = None
		return key in self._keys

	def has_key(self, key):
		return key in self

	def __len__(self):
		count = 0
		for x in self:
			count += 1
		return count

	__iter__ = alias_class_method("iterkeys")


class ProtectedDict(UserDict.DictMixin):

	"""Mapping wrapper to store changes to a dict without modifying the initial dict

	given an initial dict, this wraps that dict storing changes in a secondary dict, protecting
	the underlying dict from changes
	"""

	__slots__ = ("orig", "new", "blacklist")

	def __init__(self, orig):
		self.orig = orig
		self.new = {}
		self.blacklist = {}

	def __setitem__(self, key, val):
		self.new[key] = val
		if key in self.blacklist:
			del self.blacklist[key]

	def __getitem__(self, key):
		if key in self.new:
			return self.new[key]
		if key in self.blacklist:
			raise KeyError(key)
		return self.orig[key]

	def __delitem__(self, key):
		if key in self.new:
			del self.new[key]
			return
		elif key in self.orig:
			if key not in self.blacklist:
				self.blacklist[key] = True
				return
		raise KeyError(key)

	def __iter__(self):
		for k in self.new.iterkeys():
			yield k
		for k in self.orig.iterkeys():
			if k not in self.blacklist and k not in self.new:
				yield k

	def keys(self):
		return list(self.__iter__())

	def __contains__(self, key):
		return key in self.new or (key not in self.blacklist and key in self.orig)

	has_key = __contains__

class ImmutableDict(dict):

	"""Immutable Dict, non changable after instantiating"""

	def __delitem__(self, *args):
		raise TypeError("non modifiable")

	__setitem__ = __delitem__
	clear = __delitem__
	update = __delitem__
	pop = __delitem__
	popitem = __delitem__
	setdefault = __delitem__

	def __hash__(self):
		k = self.items()
		k.sort(lambda x, y: cmp(x[0], y[0]))
		return hash(tuple(k))

	__delattr__ = __setitem__
	__setattr__ = __setitem__


class IndeterminantDict(dict):

	"""A wrapped dict with a constant dict, and a fallback function to pull keys"""

	__slots__ = ("__initial", "__pull")

	def __init__(self, pull_func, starter_dict=None):
		if starter_dict is None:
			self.__initial = {}
		else:
			self.__initial = starter_dict
		self.__pull = pull_func

	def __getitem__(self, key):
		if key in self.__initial:
			return self.__initial[key]
		else:
			return self.__pull(key)

	def get(self, key, val=None):
		try:
			return self[key]
		except KeyError:
			return val

	def __hash__(self):
		raise TypeError("non hashable")

	def __delitem__(self, *args):
		raise TypeError("non modifiable")

	clear = update = pop = popitem = setdefault = __setitem__ = __delitem__
	__iter__ = keys = values = __len__ = __delitem__


class StackedDict(UserDict.DictMixin):

	"""A non modifiable dict that makes multiple dicts appear as one"""

	def __init__(self, *dicts):
		self._dicts = dicts

	def __getitem__(self, key):
		for x in self._dicts:
			if key in x:
				return x[key]
		raise KeyError(key)

	def keys(self):
		return list(iter(self))

	def iterkeys(self):
		s = set()
		for k in ifilterfalse(s.__contains__, chain(*map(iter, self._dicts))):
			s.add(k)
			yield k

	__iter__ = alias_class_method("iterkeys")

	def has_key(self, key):
		for x in self._dicts:
			if key in x:
				return True
		return False

	def __setitem__(self, *a):
		raise TypeError("non modifiable")

	__delitem__ = clear = __setitem__
