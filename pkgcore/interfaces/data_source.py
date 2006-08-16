# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
data source.

Think of it as a far more minimal form of file protocol
"""

import os

class base(object):
	"""base class, all implementations should match this protocol"""
	get_path = get_data = set_data = None


class local_source(base):
	
	"""locally accessible data source"""
	
	__slots__ = ("path",)

	def __init__(self, path):
		"""@param path: file path of the data source"""
		self.path = path

	def get_path(self):
		if os.path.exists(self.path):
			return self.path
		return None

	def get_data(self):
		if self.path is None:
			return None
		try:
			f = open(fp, "r", 32768)
			d = f.read()
			f.close()
			return d
		except OSError:
			return None


class data_source(base):
	
	def __init__(self, data):
		"""@param data: data to wrap"""
		self.data = data
	
	get_path = None
	
	def get_data(self):
		return self.data

	def set_data(self, data):
		self.data = data
