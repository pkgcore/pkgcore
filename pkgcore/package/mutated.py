# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import itertools, operator
from collections import deque
from pkgcore.util.compatibility import any, all
from pkgcore.util.iterables import caching_iter, iter_sort
from pkgcore.resolver.pigeonholes import PigeonHoledSlots
from pkgcore.resolver.choice_point import choice_point
from pkgcore.util.currying import pre_curry, post_curry
from pkgcore.restrictions import packages, values, restriction

class MutatedPkg(object):
	__slots__ = ("pkg, "overrides")
	
	def __init__(self, pkg, overrides}
		"""pkg is a pkg to wrap, overrides is an attr -> instance list to fake """
		self._pkg = pkg
		self._overrides = overrides
		
	def __getattr__(self, attr):
		if attr in self._overrides:
			return self._overrides[attr]
		return getattr(self._pkg, attr)

	def __cmp__(self, other):
		if isinstance(other, self.__class__):
			return cmp(self._pkg, other._pkg)
		return cmp(self._pkg, other)
