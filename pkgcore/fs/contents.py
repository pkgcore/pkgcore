# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
contents set- container of fs objects
"""

from itertools import imap
from pkgcore.fs import fs
from pkgcore.util.compatibility import any, all
from itertools import chain

def check_instance(obj):
	if not isinstance(obj, fs.fsBase):
		raise TypeError("'%s' is not a fs.fsBase deriviative" % obj)
	return obj


class contentsSet(set):
	"""set of L{fs<pkgcore.fs.fs>} objects"""

	def __new__(cls, *a, **kw):
		# override __new__ so set doesn't scream about opt args
		return set.__new__(cls)

	def __init__(self, initial=None, frozen=False):
		
		"""
		@param initial: initial fs objs for this set
		@type initial: sequence
		@param frozen: controls if it modifiable after initialization
		"""
		
		if initial is None:
			initial = []
		set.__init__(self, imap(check_instance, initial))
		self.frozen = frozen

	def add(self, obj):

		"""
		add a new fs obj to the set
		
		@param obj: must be a derivative of L{pkgcore.fs.fs.fsBase}
		"""
		
		if self.frozen:
			# weird, but keeping with set.
			raise AttributeError("%s is frozen; no add functionality" % self.__class__)
		if not isinstance(obj, fs.fsBase):
			raise TypeError("'%s' is not a fs.fsBase class" % str(obj))
		set.add(self, obj)

	def remove(self, obj):

		"""
		remove a fs obj to the set
		
		@param obj: must be a derivative of L{pkgcore.fs.fs.fsBase}, or a string location of an obj in the set
		@raise KeyError: if the obj isn't found
		"""
		
		if self.frozen:
			# weird, but keeping with set.
			raise AttributeError("%s is frozen; no remove functionality" % self.__class__)
		if not isinstance(obj, fs.fsBase):
			# why are we doing the loop and break?  try this
			# s=set([1,2,3]);
			# for x in s:s.remove(x)
			# short version, you can't yank stuff while iterating over the beast.
			# iow, what you think would be cleaner/simpler here, doesn't work. :)
			# ~harring

			if obj is not None:
				for x in self:
					if obj == x.location:
						set.remove(self, x)
						return
			raise KeyError(obj)
		else:
			set.remove(self, obj)

	def __contains__(self, key):
		if isinstance(key, fs.fsBase):
			return set.__contains__(self, key)
		for x in self:
			if key == x.location:
				return True
		return False

	def clear(self):
		"""
		clear the set
		@raise ttributeError: if the instance is frozen
		"""
		if self.frozen:
			# weird, but keeping with set.
			raise AttributeError("%s is frozen; no clear functionality" % self.__class__)
		set.clear(self)

	def difference(self, other):
		if isinstance(other, contentsSet):
			return contentsSet((x for x in self if x.location not in other))
		return set.difference(self, other)
	
	def intersection(self, other):
		if isinstance(other, contentsSet):
			return contentsSet((x for x in self if x.location in other))
		return set.intersection(self, other)
	
	def issubset(self, other):
		if isinstance(other, contentsSet):
			return all(x.location in other for x in self)
		return set.issubset(self, other)
	
	def issuperset(self, other):
		return other.issubset(self)
	
	def union(self, other):
		if isinstance(other, contentsSet):
			return contentsSet(chain(iter(self), (x for x in other if x.location not in self)))
		return set.union(self, other)
	
	def symmetric_difference(self, other):
		i = self.intersection(other)
		return contentsSet(chain(iter(self.difference(i)), iter(other.difference(i))))

	def iterfiles(self, invert=False):
		return (x for x in self if isinstance(x, fs.fsFile) is not invert)

	def files(self, invert=False):
		return list(self.iterfiles(invert=invert))

	def iterdirs(self, invert=False):
		return (x for x in self if isinstance(x, fs.fsDir) is not invert)

	def dirs(self, invert=False):
		return list(self.iterdirs(invert=invert))

	def iterlinks(self, invert=False):
		return (x for x in self if isinstance(x, fs.fsLink) is not invert)

	def links(self, invert=False):
		return list(self.iterlinks(invert=invert))

	def iterdevs(self, invert=False):
		return (x for x in self if isinstance(x, fs.fsDev) is not invert)

	def devs(self, invert=False):
		return list(self.iterdevs(invert=invert))

	def iterfifos(self, invert=False):
		return (x for x in self if isinstance(x, fs.fsFifo) is not invert)

	def fifos(self, invert=False):
		return list(self.iterfifos(invert=invert))

	for k in ("files", "dirs", "links", "devs", "fifos"):
		s = k.capitalize()
		locals()[k].__doc__ = \
			"""
			returns a list of just L{pkgcore.fs.fs.fs%s} instances
			@param invert: if True, yield everything that isn't a fs%s instance, else yields just fs%s
			""" % (s.rstrip("s"), s, s)
		locals()["iter"+k].__doc__ = \
			"""
			a generator yielding just L{pkgcore.fs.fs.fs%s} instances
			@param invert: if True, yield everything that isn't a fs%s instance, else yields just fs%s
			""" % (s.rstrip("s"), s, s)
		del s
	del k
		
