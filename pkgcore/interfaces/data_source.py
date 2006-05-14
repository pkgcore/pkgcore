# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os

class base(object):
	def get_data(self, arg):
		raise NotImplementedError
	get_path = get_data

class local_source(base):
	__slots__ = ("path",)

	def __init__(self, path):
		self.path = path


	def get_path(self):
		if os.path.exists(self.path):
			return self.path
		return None


	def get_data(self):
		if self.path == None:
			return None
		try:
			f = open(fp, "r")
			d = f.read()
			f.close()
			return d
		except OSError:
			return None
