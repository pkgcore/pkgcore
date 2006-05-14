# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# Copyright: 2000-2005 Gentoo Foundation
# License: GPL2

from pkgcore.fs.util import normpath
import os, sys
from pkgcore.interfaces import data_source

class base(object):	pass

class cache(base):
	"""
	Maintains the cache information about eclasses available to an ebuild.
	get_path and get_data are special- one (and only one) can be set to None.
	Any code trying to get eclass data/path will choose which method it prefers, falling back to what's available if only one option
	exists.

	get_path should be defined when it's possible to state the actual on disk location
	get_data should be defined when it's not possible (or not preferable), as such
	dumping the eclass down the pipe is required (think remote tree)

	Base defaults to having both set.  Override as needed.
	Set to None if that method isn't possible.
	"""
	def __init__(self, porttree, *additional_porttrees):
		self.eclasses = {} # {"Name": ("location","_mtime_")}

		self.porttrees = tuple(map(normpath, [porttree] + list(additional_porttrees)))
		self._master_eclass_root = os.path.join(self.porttrees[0], "eclass")
		self.update_eclasses()


	def update_eclasses(self):
		"""force instance to update it's internal view of on disk/remote eclasses"""
		self.eclasses = {}
		eclass_len = len(".eclass")
		for x in [normpath(os.path.join(y, "eclass")) for y in self.porttrees]:
			if not os.path.isdir(x):
				continue
			for y in [y for y in os.listdir(x) if y.endswith(".eclass")]:
				try:
					mtime = os.stat(x+"/"+y).st_mtime
				except OSError:
					continue
				ys = y[:-eclass_len]
				self.eclasses[ys] = (x, long(mtime))


	def is_eclass_data_valid(self, ec_dict):
		"""given a dict as returned by get_eclass_data, walk it comparing it to internal eclass view
		returns a boolean representing whether that eclass data is still up to date, or not
		"""
		for eclass, tup in ec_dict.iteritems():
			if eclass not in self.eclasses or tuple(tup) != self.eclasses[eclass]:
				return False

		return True


	def get_eclass_data(self, inherits, from_master_only=False):
		"""given a list of inherited eclasses, return the cachable eclass entries
		only make get_eclass_data calls for data you know came from this eclass_cache, otherwise be ready to cache a KeyError
		exception for any eclass that was requested, but not known to this cache
		"""

		ec_dict = {}
		for x in inherits:
			try:
				ec_dict[x] = self.eclasses[x]
			except:
				print "ec=", ec_dict
				print "inherits=", inherits
				raise
			if from_master_only and self.eclasses[x][0] != self._master_eclass_root:
				return None

		return ec_dict

	def get_eclass_path(self, eclass):
		"""get local file path to an eclass.  remote implementations should set this to None, since the file isn't locally available"""
		try:
			return os.path.join(self.eclasses[eclass][0], eclass+".eclass")
		except KeyError:
			return None

