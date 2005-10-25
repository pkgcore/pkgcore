# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id:$

import fs

class contentsSet(set):
	"""class wrapping a contents file"""

	def __init__(self, initial=None):
		l = set()
		if initial is not None:
			for x in initial:
				if not isinstance(obj, fs.fsBase):
					raise TypeError("'%s' is not a fs.fsBase deriviative" % x)
				l.add(x.location)
		else:
			initial = []
		set.__init__(self, initial)
		self.locations = l
	

	def add(self, obj):
		if not isinstance(obj, fs.fsBase):
			raise Exception("'%s' is not a fs.fsBase class" % str(obj))
		self.locations.add(obj.location)
		set.add(self, obj)
		

	def remove(self, obj):
		if not isinstance(obj, fs.fsBase):
			# why are we doing the loop and break?  try this
			# s=set([1,2,3]);
			# for x in s:s.remove(x)
			# short version, you can't yank stuff while iterating over the beast.
			# iow, what you think would be cleaner/simpler here, doesn't work. :)
			# ~harring
			for x in self:
				if obj == x.location:
					self.locations.remove(x.location)
					set.remove(self, x)
					return
			if key == None:
				raise KeyError(obj)
		else:
			self.locations.remove(obj.location)
			set.remove(self, obj)
				

	def __contains__(self, key):
		if isinstance(obj, fs.fsBase):
			return set.__contains__(self, key)
		return key in self.locations
	
	def clear(self):
		self.locations.clear()
		set.clear(self)

	def iterfiles(self):
		return (x for x in self if isinstance(x, fs.fsFile))


	def files(self):
		return list(self.iterfiles())


	def iterdirs(self):
		return (x for x in self if isinstance(x, fs.fsDir))


	def dirs(self):
		return list(self.iterdirs())


	def iterlinks(self):
		return (x for x in self if isinstance(x, fs.fsLink))


	def links(self):
		return list(self.iterlinks())


	def devs(self):
		return list(self.iterdevs())


	def iterdevs(self):
		return (x for x in self if isinstance(x, fs.fsDev))


	def fifos(self):
		return list(self.iterfifos())


	def iterfifos(self):
		return (x for x in self if isinstance(x, fs.fsFifo))


