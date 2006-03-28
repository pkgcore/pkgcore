# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from weakref import WeakValueDictionary
import warnings

class_hits = {}
class_misses = {}

class WeakInstMeta(type):

	def __new__(cls, name, bases, d):
		if d.get("__inst_caching__", False):
			d["__inst_caching__"] = True
			d["__inst_dict__"]  = WeakValueDictionary()
		else:
			d["__inst_caching__"] = False
		slots = d.get('__slots__')
		if slots is not None:
			for base in bases:
				if getattr(base, '__weakref__', False):
					break
			else:
				d['__slots__'] = tuple(slots) + ('__weakref__',)
		return type.__new__(cls, name, bases, d)

	def __call__(cls, *a, **kw):
		"""disable caching via disable_inst_caching=True"""
		if cls.__inst_caching__ and not kw.pop("disable_inst_caching", False):
			kwlist = kw.items()
			kwlist.sort()
			try:
				key = hash((a, tuple(kwlist)))
			except TypeError, t:
				warnings.warn("caching keys for %s, got %s for a=%s, kw=%s" % (cls, t, a, kw))
				del t
				key = None
				instance = None
			else:
				instance = cls.__inst_dict__.get(key)

			if instance is None:
				class_misses[cls] = class_misses.get(cls, 0) + 1
				instance = super(WeakInstMeta, cls).__call__(*a, **kw)

				if key is not None:
					cls.__inst_dict__[key] = instance
			else:
				class_hits[cls] = class_hits.get(cls, 0) + 1
		else:
			instance = super(WeakInstMeta, cls).__call__(*a, **kw)

#		print cls
#		print a
#		print kw

		return instance
