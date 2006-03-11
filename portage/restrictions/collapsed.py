# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2
# $Id: collapsed.py 2282 2005-11-10 00:30:30Z ferringb $

__all__=("DictBased")
from portage.restrictions import packages

class DictBased(packages.base):

	"""Restrictions are (by default) executed in a depth/breadth method; for long chains of restrictions,
	this grows inneficient.  For example, package.mask'ing has over 300 atoms, effectively over 1800 objects in use.
	
	Running the filter on each package instance returned from a repo would be exceedingly slow, a way to get as close to
	constant lookup as possible is needed.
	
	DictBased works by using supplied functions to collapse long chains of restrictions into a dict, with key 
	defined by get_key_from_atom (with get_key_from_package returning the key of a pkg instance), and with the 
	value of that key holding the remaining restrictions (if any).
	
	Common usage at this point is to collapse category and package attribute restrictions into constant lookup, with 
	any remaining version restrictions being handed off as a val.
	
	Example usage of this class should be available in portage.config.domain.domain

	Aside from that, method of generating keys/collapsing restrictions is subject to change, still need to push metadata 
	in re: what restriction types are being collapsed; short version, api isn't declared stable yet.
	"""

	__slots__ = tuple(["restricts_dict", "get_pkg_key", "get_atom_key"] + packages.base.__slots__)

	def __init__(self, restriction_items, get_key_from_package, get_key_from_atom, *args, **kwargs):
		"""restriction_items is a source of restriction keys and remaining restriction (if none, set it to None)
		get_key is a function to get the key from a pkg instance"""

		if not callable(get_key_from_package):
			raise TypeError(get_key_from_package)

		super(DictBased, self).__init__(*args, **kwargs)
		self.restricts_dict = {}
		for r in restriction_items:
			key, remaining = get_key_from_atom(r)
			if not remaining:
				remaining = packages.AlwaysTrue
			else:
				if len(remaining) == 1 and (isinstance(remaining, list) or isinstance(remaining, tuple)):
					remaining = remaining[0]
				elif isinstance(remaining, (tuple, list)):
					remaining = packages.AndRestriction(*remaining)
				elif not isinstance(remaining, base):
					print "remaining=",remaining
					print "base=",base
					raise KeyError("unable to convert '%s', remaining '%s' isn't of a known base" % (str(r), str(remaining)))

			if key in self.restricts_dict:
				self.restricts_dict[key].add_restriction(remaining)
			else:
				self.restricts_dict[key] = packages.OrRestriction(remaining)

		self.get_pkg_key, self.get_atom_key = get_key_from_package, get_key_from_atom


	def match(self, pkginst):
		try:
			key = self.get_pkg_key(pkginst)
		except (TypeError, AttributeError):
			return self.negate
		if key not in self.restricts_dict:
			return self.negate
	
		remaining = self.restricts_dict[key]
		return remaining.match(pkginst) ^ self.negate

			
	def __contains__(self, restriction):
		if isinstance(restriction, base):
			key, r = self.get_atom_key(restriction)
		if key != None and key in self.restricts_dict:
			return True
		return False

	def __str__(self):
		return "%s: pkg_key(%s), atom_key(%s)" % (self.__class__, self.get_pkg_key, \
			self.get_atom_key)

#	def __getitem__(self, restriction, default=None):
#		if isinstance(restriction, base):
#			key, r = self.get_atom_key(restriction)
#		if key == None:	return default
#		return self.restricts_dict.get(key, default)
#		
#
#	def __setitem__(self, restriction, val):
#		if isinstance(restriction, base):
#			key, r = self.get_atom_key(restriction)
#		if key == None:
#			raise KeyError("either passed in, or converted val became None, invalid as key")
#		self.restricts_dict[key] = val
#
#
#	def __delitem__(self, restriction):
#		if isinstance(restriction, base):
#			key = self.get_atom_key(restriction)
#		if key != None and key in self.restricts_dict:
#			del self.restricts_dict[key]
