# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
anydbm backend
"""

anydbm_module = __import__("anydbm")
try:
	import cPickle as pickle
except ImportError:
	import pickle
import os
import fs_template
import cache_errors


class database(fs_template.FsBased):

	"""anydbm based cache backend, autocommiting"""
	
	autocommits = True
	cleanse_keys = True

	def __init__(self, *args, **config):
		self._db = None
		super(database,self).__init__(*args, **config)

		default_db = config.get("dbtype","anydbm")
		if not default_db.startswith("."):
			default_db = '.' + default_db

		self._db_path = os.path.join(self.location, fs_template.gen_label(self.location, self.label)+default_db)
		self._db = None

		try:
			self._db = anydbm_module.open(self._db_path, "w", self._perms)
		except anydbm_module.error:
			# XXX handle this at some point
			try:
				self._ensure_dirs()
				self._ensure_dirs(self._db_path)
				self._ensure_access(self._db_path)
			except (OSError, IOError), e:
				raise cache_errors.InitializationError(self.__class__, e)

			# try again if failed
			try:
				if self._db is None:
					self._db = anydbm_module.open(self._db_path, "c", self._perms)
			except andbm_module.error, e:
				raise cache_errors.InitializationError(self.__class__, e)
	__init__.__doc__ = fs_template.FsBased.__init__.__doc__
	
	def iteritems(self):
		return self._db.iteritems()

	def _getitem(self, cpv):
		# we override getitem because it's just a cpickling of the data handed in.
		return pickle.loads(self._db[cpv])

	def _setitem(self, cpv, values):
		self._db[cpv] = pickle.dumps(values,pickle.HIGHEST_PROTOCOL)

	def _delitem(self, cpv):
		del self._db[cpv]

	def iterkeys(self):
		return iter(self._db)

	def __contains__(self, cpv):
		return cpv in self._db

	def __del__(self):
		if self._db is not None:
			self._db.sync()
			self._db.close()
