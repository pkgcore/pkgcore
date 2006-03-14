# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

class base(object):
	pass

	def get_data(self, bashrc):
		raise NotImplementedError
	
	get_path = get_data

class ProfileException(Exception):
	def __init__(self, err):	self.err = err
	def __str__(self): return str(self.err)
