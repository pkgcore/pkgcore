# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

class CacheError(Exception):	pass

class InitializationError(CacheError):
	def __init__(self, class_name, error):
		self.error, self.class_name = error, class_name
	def __str__(self):
		return "Creation of instance %s failed due to %s" % \
			(self.class_name, str(self.error))


class CacheCorruption(CacheError):
	def __init__(self, key, ex):
		import traceback;traceback.print_stack()
		self.key, self.ex = key, ex
	def __str__(self):
		return "%s is corrupt: %s" % (self.key, str(self.ex))


class GeneralCacheCorruption(CacheError):
	def __init__(self,ex):	self.ex = ex
	def __str__(self):	return "corruption detected: %s" % str(self.ex)


class InvalidRestriction(CacheError):
	def __init__(self, key, restriction, exception=None):
		if exception == None:	exception = ''
		self.key, self.restriction, self.ex = key, restriction, ex
	def __str__(self):
		return "%s:%s is not valid: %s" % \
			(self.key, self.restriction, str(self.ex))


class ReadOnlyRestriction(CacheError):
	def __init__(self, info=''):
		self.info = info
	def __str__(self):
		return "cache is non-modifiable"+str(self.info)
