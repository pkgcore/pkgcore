# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: mappings.py 2000 2005-09-18 13:54:10Z ferringb $

from itertools import imap
import UserDict

class IndexableSequence(object):
	def __init__(self, get_keys, get_values, recursive=False, returnEmpty=False, 
			returnIterFunc=None, modifiable=False, delfunc=None, updatefunc=None):
		self.__get_keys = get_keys
		self.__get_values = get_values
		self.__cache = {}
		self.__cache_complete = False
		self.__cache_can_be_complete = not recursive and not modifiable
		self.__return_empty = returnEmpty
		self.__returnFunc = returnIterFunc
		self._frozen = not modifiable
		if not self._frozen:
			self.__del_func = delfunc
			self.__update_func = updatefunc


	def __getitem__(self, key):
		if not (self.__cache_complete or self.__cache.has_key(key)):
			self.__cache[key] = self.__get_values(key)
		return self.__cache[key]


	def keys(self):
		return list(self.iterkeys())

	
	def __delitem__(self, key):
		if self._frozen:
			raise AttributeError
		if not key in self:
			raise KeyError(key)
		return self.__del_func(key)


	def __setitem__(self, key, value):
		if self._frozen:
			raise AttributeError
		if not key in self:
			raise KeyError(key)
		return self.__update_func(key, value)


	def __contains__(self, key):
		try:	
			self[key]
			return True
		except KeyError:
			return False


	def iterkeys(self):
		if self.__cache_complete:
			return self.__cache.keys()
		return self.__gen_keys()


	def __gen_keys(self):
		for key in self.__get_keys():
			if not self.__cache.has_key(key):
				self.__cache[key] = self.__get_values(key)
			yield key
		self.__cache_complete = self.__cache_can_be_complete
		return


	def __iter__(self):
		if self.__returnFunc:
			for key, value in self.iteritems():
				if len(value) == 0:
					if self.__return_empty:
						yield key
				else:
					for x in value:
						yield self.__returnFunc(key, x)
		else:
			for key, value in self.iteritems():
				if len(value) == 0:
					if self.__return_empty:
						yield key
				else:
					for x in value:
						yield key+'/'+x
		return


	def items(self):
		return list(self.iteritems())
	

	def iteritems(self):
		if self.__cache_complete:
			return self.__cache.items()
		return self.__gen_items()


	def __gen_items(self):
		for key in self.iterkeys():
			yield key, self[key]
		return


class LazyValDict(UserDict.DictMixin):
	"""
	given a function to get keys, and to look up the val for those keys, it'll 
	lazy load key definitions, and values as requested
	"""
	def __init__(self, get_keys_func, get_val_func):
		"""
		get_keys_func is a callable that is JIT called with no args  returns a tuple of keys, or is a list
		get_val_func is a callable that is JIT called with the key requested
		"""
		if not callable(get_val_func):
			raise TypeError("get_val_func isn't a callable")
		if callable(get_keys_func):
			self.__keys_func = get_keys_func
		else:
			try:
				self.__keys = set(get_keys_func)
				self.__keys_func = None
			except TypeError:
				if not callable(get_keys_func):
					raise TypeError("get_keys_func isn't iterable nor is it callable")
				self.__keys_func = get_keys_func
				self.__keys = None
		self.__val_func = get_val_func
		self.__vals = {}


	def __setitem__(self):
		raise AttributeError


	def __delitem__(self):
		raise AttributeError


	def __getitem__(self, key):
		if self.__keys_func != None:
			self.__keys = set(self.__keys_func())
			self.__keys_func = None
		if key in self.__vals:
			return self.__vals[key]
		if key in self.__keys:
			v = self.__vals[key] = self.__val_func(key)
			self.__keys.remove(key)
			return v
		raise KeyError(key)


	def keys(self):
		if self.__keys_func != None:
			self.__keys = set(self.__keys_func())
			self.__keys_func = None
		l = list(self.__keys)
		l.extend(self.__vals.keys())
		return l


	def has_key(self, key):
		if self.__keys_func != None:
			map(self.__keys.setdefault, self.__keys_func())
			self.__keys_func = None
		return key in self.__keys or key in self.__vals


class ProtectedDict(UserDict.DictMixin):
	"""
	given an initial dict, this wraps that dict storing changes in a secondary dict, protecting
	the underlying dict from changes
	"""
	__slots__=("orig","new","blacklist")

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


	def has_key(self, key):
		return key in self.new or (key not in self.blacklist and key in self.orig)


class Unchangable(Exception):
	def __init__(self, key):	self.key = key
	def __str__(self):			return "key '%s' is unchangable" % self.key


class InvertedContains(set):
	"""negate the __contains__ return from a set
	mainly useful in conjuection with LimitedChangeSet for converting from blacklist to whitelist
	"""
	def __contains__(self, key):
		return not set.__contains__(self, key)

class LimitedChangeSet(object):
	"""
	set that supports limited changes, specifically deleting/adding a key only once per commit, 
	optionally blocking changes to certain keys.
	"""
	_removed 	= 0
	_added		= 1

	def __init__(self, initial_keys, unchangable_keys=None):
		self.__new = set(initial_keys)
		if unchangable_keys == None:
			self.__blacklist = []
		else:
			if isinstance(unchangable_keys, (list, tuple)):
				unchangable_keys = set(unchangable_keys)
			self.__blacklist = unchangable_keys
		self.__changed = set()
		self.__change_order = []
		self.__orig = frozenset(self.__new)

	def add(self, key):
		if key in self.__changed or key in self.__blacklist:
			# it's been del'd already once upon a time.
			raise Unchangable(key)

		self.__new.add(key)
		self.__changed.add(key)
		self.__change_order.append((self._added, key))

	def remove(self, key):
		if key in self.__changed or key in self.__blacklist:
			raise Unchangable(key)
		
		if key in self.__new:
			self.__new.remove(key)
		self.__changed.add(key)
		self.__change_order.append((self._removed, key))

	def __contains__(self, key):
		return key in self.__new

	def changes_count(self):
		return len(self.__change_order)

	def commit(self):
		self.__orig = frozenset(self.__new)
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
				self.__new.add(key)
			else:
				self.__new.remove(key)					
			l -= 1

	def __str__(self):
		return str(self.__new).replace("set(","LimitedChangeSet(", 1)

	def __iter__(self):
		return iter(self.__new)

	def __len__(self):
		return len(self.__new)


class ImmutableDict(dict):
	"""Immutable Dict, non changable after instantiating"""

	def __delitem__(self, *args):
		raise TypeError("non modifiable")

	__setitem__ = __delitem__
	clear = __delitem__
	
	def __hash__(self):
		k = self.items()
		k.sort(lambda x, y: cmp(x[0], y[0]))
		return hash(tuple(k))
	
	__delattr__ = __setitem__
	__setattr__ = __setitem__
