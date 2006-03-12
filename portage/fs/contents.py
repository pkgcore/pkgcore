# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import fs
from itertools import imap

def check_instance(obj):
	if not isinstance(obj, fs.fsBase):
		raise TypeError("'%s' is not a fs.fsBase deriviative" % obj)
	return obj

class contentsSet(set):
	"""class wrapping a contents file"""

	def __new__(cls, *a, **kw):
		# override __new__ so set doesn't scream about opt args
		return set.__new__(cls)

	def __init__(self, initial=None):
		if initial is None:
			initial = []
		set.__init__(self, imap(check_instance, initial))
	
	def add(self, obj):
		if not isinstance(obj, fs.fsBase):
			raise Exception("'%s' is not a fs.fsBase class" % str(obj))
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
					set.remove(self, x)
					return
			if key == None:
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
