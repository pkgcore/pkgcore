anydbm_module = __import__("anydbm")
import cPickle, os
import fs_template
import cache_errors


class database(fs_template.FsBased):

	autocommits = True

	def __init__(self, label, auxdbkeys, **config):
		super(database,self).__init__(label, auxdbkeys, **config)

		default_db = config.get("dbtype","anydbm")
		if not default_db.startswith("."):
			default_db = '.' + default_db

		self._db_path = os.path.join(self._base, fs_template.gen_label(self._base, self.label)+default_db)
		print "opening self._db_path=",self._db_path
		self.__db = None
		try:
			self.__db = anydbm_module.open(self._db_path, "w", self._perms)
			try:
				self._ensure_dirs()
				self._ensure_dirs(self._db_path)
				self._ensure_access(self._db_path)
				
			except (OSError, IOError), e:
				raise cache_errors.InitializationError(self.__clas__, e)
			# try again if failed
			if self.__db == None:
				self.__db = anydbm_module.open(self._db_path, "c", self._perms)


		except anydbm_module.error, e:
			# XXX handle this at some point
			raise


	def __getitem__(self, cpv):
		# we override getitem because it's just a cpickling of the data handed in.
		return cPickle.loads(self.__db[cpv])


	def _setitem(self, cpv, values):
		self.__db[cpv] = cPickle.dumps(values,cPickle.HIGHEST_PROTOCOL)

	def _delitem(self, cpv):
		del self.__db[cpv]


	def iterkeys(self):
		return iter(self.__db)


	def has_key(self, cpv):
		return cpv in self.__db

	def commit(self):	pass

	def __del__(self):
		print "keys=",self.__db.keys()
		self.__db.sync()
		self.__db.close()
