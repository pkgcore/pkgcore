# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# Copyright: 2000-2005 Gentoo Foundation
# License: GPL2

"""
in memory representation of on disk eclass stacking order
"""

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

	get_path should be defined when it's possible to state the actual on disk location
	get_data should be defined when it's not possible (or not preferable), as such
	dumping the eclass down the pipe is required (think remote tree)

	Base defaults to having both set.  Override as needed.
	Set to None if that method isn't possible.
	"""
	def __init__(self, porttree):
		"""
		@param porttree: ondisk location of the tree we're working with
		"""
		self.eclasses = {} # {"Name": ("location","_mtime_")}
		self.porttree = normpath(porttree)
		self.update_eclasses()


	def update_eclasses(self):
		"""force instance to update it's internal view of on disk/remote eclasses"""
		self.eclasses = {}
		eclass_len = len(".eclass")
		fp = os.path.join(self.porttree, "eclass")
		if os.path.isdir(x):
			for y in os.listdir(fp):
				if not y.endswith(".eclass"):
					continue
				try:
					mtime = os.stat(fp+"/"+y).st_mtime
				except OSError:
					continue
				ys = y[:-eclass_len]
				self.eclasses[ys] = (fp, long(mtime))


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
				print "inherits=", inherits
				raise

		return ec_dict

	def get_eclass_path(self, eclass):
		"""get local file path to an eclass.  remote implementations should set this to None, since the file isn't locally available"""
		try:
			return os.path.join(self.eclasses[eclass][0], eclass+".eclass")
		except KeyError:
			return None


class StackedCache(cache):

	"""
	collapse multiple eclass caches into one, doing L->R searching for eclass matches
	"""
	def __init__(self, *caches):
		"""
		@param caches: L{cache} instances to stack; ordering should be desired lookup order
		"""
		if len(caches) < 2:
			raise TypeError("%s requires at least two eclass_caches" % self.__class__)
		self.eclasses = StackedDict(*[ec.eclasses for ec in caches])
