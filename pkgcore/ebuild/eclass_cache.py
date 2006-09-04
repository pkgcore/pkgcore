# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# Copyright: 2000-2005 Gentoo Foundation
# License: GPL2

"""
in memory representation of on disk eclass stacking order
"""

import os
from pkgcore.interfaces.data_source import local_source
from pkgcore.config.introspect import ConfigHint

from pkgcore.util.demandload import demandload
demandload(globals(), "pkgcore.fs.util:normpath pkgcore.util.mappings:StackedDict os")

class base(object):
	pass

class cache(base):
	"""
	Maintains the cache information about eclasses available to an ebuild.
	get_path and get_data are special- one (and only one) can be set to None.
	Any code trying to get eclass data/path will choose which method it prefers, falling back to what's available if only one option
	exists.

	dumping the eclass down the pipe is required (think remote tree)

	Base defaults to having both set.  Override as needed.
	Set to None if that method isn't possible.
	"""
	
	pkgcore_config_type = ConfigHint({"path":"str", "portdir":"str"})

	def __init__(self, path, portdir=None):
		"""
		@param porttree: ondisk location of the tree we're working with
		"""
		# generate this.
		# self.eclasses = {} # {"Name": ("location","_mtime_")}
		self.eclassdir = normpath(path)
		self.portdir = portdir
		self.update_eclasses()

	def update_eclasses(self):
		"""force instance to update it's internal view of on disk/remote eclasses"""
		self.eclasses = {}
		eclass_len = len(".eclass")
		pjoin = os.path.join
		if os.path.isdir(self.eclassdir):
			for y in os.listdir(self.eclassdir):
				if not y.endswith(".eclass"):
					continue
				try:
					mtime = os.stat(pjoin(self.eclassdir, y)).st_mtime
				except OSError:
					continue
				ys = y[:-eclass_len]
				self.eclasses[ys] = (self.eclassdir, long(mtime))


	def is_eclass_data_valid(self, ec_dict):
		"""given a dict as returned by get_eclass_data, walk it comparing it to internal eclass view
		returns a boolean representing whether that eclass data is still up to date, or not
		"""
		for eclass, tup in ec_dict.iteritems():
			if eclass not in self.eclasses or tuple(tup) != self.eclasses[eclass]:
				return False

		return True


	def get_eclass_data(self, inherits):
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
				print "inherit=",x
				raise

		return ec_dict

	def get_eclass(self, eclass):
		o = self.eclasses.get(eclass, None)
		if o is None:
			return o
		return local_source(os.path.join(o[0], eclass+".eclass"))
		

class StackedCaches(cache):

	"""
	collapse multiple eclass caches into one, doing L->R searching for eclass matches
	"""
	
	pkgcore_config_type = ConfigHint({"caches":"section_refs", "portdir":"str", "eclassdir":"str"})
	
	def __init__(self, caches, **kwds):
		"""
		@param caches: L{cache} instances to stack; ordering should be desired lookup order
		@keyword eclassdir: override for the master eclass dir, required for eapi0 and idiot eclass usage.  defaults to pulling from the first cache
		"""
		if len(caches) < 2:
			raise TypeError("%s requires at least two eclass_caches" % self.__class__)
		
		self.eclassdir = kwds.pop("eclassdir", None)
		if self.eclassdir is None:
			self.eclassdir = caches[0].eclassdir

		self.portdir = kwds.pop("portdir", None)
		if self.portdir is None:
			self.portdir = os.path.dirname(self.eclassdir.rstrip(os.path.sep))

		self.eclasses = StackedDict(*[ec.eclasses for ec in caches])
