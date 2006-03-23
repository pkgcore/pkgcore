# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from weakref import WeakValueDictionary
import warnings

class_hits = {}
class_misses = {}

class WeakInstCaching(object):

	__inst_caching__ = True
	
	def __new__(cls, *a, **kw):
		"""disable caching via disable_inst_caching=True"""
		global class_hits, class_misses
		if "disable_inst_caching" in kw:
			disabled = kw["disable_inst_caching"]
			del kw["disable_inst_caching"]
		else:
			disabled = False
		if cls.__inst_caching__ is not False and not disabled:
			o = None
			try:
				key = hash((cls, a, tuple(kw.iteritems())))
			except TypeError, t:
				warnings.warn("caching keys for %s, got %s for a=%s, kw=%s" % (cls, t, a, kw))
				del t
				key = None
			if cls.__inst_caching__ == True:
				cls.__inst_caching__ = WeakValueDictionary()
			elif key is not None:
				o = cls.__inst_caching__.get(key, None) 

			if o is None:
				class_misses[cls] = class_misses.get(cls, 0) + 1
				o = object.__new__(cls)
				o.__init__()
				o.__initialize__(*a, **kw)
				if key is not None:
					cls.__inst_caching__[key] = o
			else:
				class_hits[cls] = class_hits.get(cls, 0) + 1
		else:
			o = object.__new__(cls)
			o.__initialize__(*a, **kw)

#		print cls
#		print a
#		print kw

		return o

	def __init__(*a, **kw):
		pass
