# Copyright: 2005-2006 Brian Harring <ferringb@gmail.com>
# Author(s): Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
template for cache backend classes
"""

from pkgcore.cache import cache_errors
from pkgcore.util.mappings import ProtectedDict

class database(object):
	# this is for metadata/cache transfer.
	# basically flags the cache needs be updated when transfered cache to cache.
	# leave this.

	"""
	@ivar autocommits: controls whether the template commits every update, or queues up updates
	@ivar complete_eclass_entries: specifics if the cache backend stores full eclass data, or partial
	@ivar cleanse_keys: boolean controlling whether the template should drop empty keys for storing
	@ivar serialize_eclasses: boolean controlling whether the template should serialize eclass data itself, or leave it to the derivative
	"""
	
	complete_eclass_entries = True
	autocommits = False
	cleanse_keys = False
	serialize_eclasses = True

	def __init__(self, location, label, auxdbkeys, readonly=False):
		"""
		initialize the derived class; specifically, store label/keys
		
		@param location: fs location the cache is stored at
		@param label: cache label
		@param auxdbkeys: sequence of allowed keys for each cache entry
		@param readonly: defaults to False, controls whether the cache is mutable"""
		self._known_keys = auxdbkeys
		self.location = location
		self.label = label
		self.readonly = readonly
		self.sync_rate = 0
		self.updates = 0

	def __getitem__(self, cpv):
		"""set a cpv to values
		This shouldn't be overriden in derived classes since it handles the __eclasses__ conversion.
		that said, if the class handles it, they can override it."""
		if self.updates > self.sync_rate:
			self.commit()
			self.updates = 0
		d = self._getitem(cpv)
		if self.serialize_eclasses and "_eclasses_" in d:
			d["_eclasses_"] = self.reconstruct_eclasses(cpv, d["_eclasses_"])
		return d

	def _getitem(self, cpv):
		"""get cpv's values.
		override this in derived classess"""
		raise NotImplementedError

	def __setitem__(self, cpv, values):
		"""set a cpv to values
		This shouldn't be overriden in derived classes since it handles the readonly checks"""
		if self.readonly:
			raise cache_errors.ReadOnlyRestriction()
		if self.cleanse_keys:
			d = ProtectedDict(values)
			for k in d.keys():
				if d[k] == '':
					del d[k]
			if self.serialize_eclasses and "_eclasses_" in values:
				d["_eclasses_"] = self.deconstruct_eclasses(d["_eclasses_"])
		elif self.serialize_eclasses and "_eclasses_" in values:
			d = ProtectedDict(values)
			d["_eclasses_"] = self.deconstruct_eclasses(d["_eclasses_"])
		else:
			d = values
		self._setitem(cpv, d)
		if not self.autocommits:
			self.updates += 1
			if self.updates > self.sync_rate:
				self.commit()
				self.updates = 0

	def _setitem(self, name, values):
		"""__setitem__ calls this after readonly checks.  override it in derived classes
		note _eclassees_ key *must* be handled"""
		raise NotImplementedError

	def __delitem__(self, cpv):
		"""delete a key from the cache.
		This shouldn't be overriden in derived classes since it handles the readonly checks"""
		if self.readonly:
			raise cache_errors.ReadOnlyRestriction()
		if not self.autocommits:
			self.updates += 1
		self._delitem(cpv)
		if self.updates > self.sync_rate:
			self.commit()
			self.updates = 0

	def _delitem(self, cpv):
		"""__delitem__ calls this after readonly checks.  override it in derived classes"""
		raise NotImplementedError

	def __contains__(self, cpv):
		raise NotImplementedError

	def has_key(self, cpv):
		return cpv in self

	def keys(self):
		return list(self.iterkeys())

	def iterkeys(self):
		raise NotImplementedError

	def iteritems(self):
		for x in self.iterkeys():
			yield (x, self[x])

	def items(self):
		return list(self.iteritems())

	def sync(self, rate=0):
		self.sync_rate = rate
		if(rate == 0):
			self.commit()

	def commit(self):
		if not self.autocommits:
			raise NotImplementedError

	def get_matches(self, match_dict):
		"""generic function for walking the entire cache db, matching restrictions to
		filter what cpv's are returned.  Derived classes should override this if they
		can implement a faster method then pulling each cpv:values, and checking it.

		For example, RDBMS derived classes should push the matching logic down to the
		actual RDBM."""

		import re
		restricts = {}
		for key, match in match_dict.iteritems():
			# XXX this sucks.
			try:
				if isinstance(match, str):
					restricts[key] = re.compile(match).match
				else:
					restricts[key] = re.compile(match[0], match[1]).match
			except re.error, e:
				raise InvalidRestriction(key, match, e)
			if key not in self.__known_keys:
				raise InvalidRestriction(key, match, "Key isn't valid")

		for cpv in self.keys():
			cont = True
			vals = self[cpv]
			for key, match in restricts.iteritems():
				if not match(vals[key]):
					cont = False
					break
			if cont:
				yield cpv

	@staticmethod
	def deconstruct_eclasses(eclass_dict):
		"""takes a dict, returns a string representing said dict"""
		return "\t".join(["%s\t%s\t%s" % (k, v[0], str(v[1])) for k, v in eclass_dict.items()])

	@staticmethod
	def reconstruct_eclasses(cpv, eclass_string):
		"""returns a dict when handed a string generated by serialize_eclasses"""
		eclasses = eclass_string.strip().split("\t")
		if eclasses == [""]:
			# occasionally this occurs in the fs backends.  they suck.
			return {}
		if len(eclasses) % 3 != 0:
			raise cache_errors.CacheCorruption(cpv, "_eclasses_ was of invalid len %i" % len(eclasses))
		d = {}
		for x in xrange(0, len(eclasses), 3):
			d[eclasses[x]] = (eclasses[x + 1], long(eclasses[x + 2]))
		del eclasses
		return d
