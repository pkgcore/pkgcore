# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: profiles.py 1911 2005-08-25 03:44:21Z ferringb $

class base(object):
	pass

	def get_data(self, bashrc):
		raise NotImplementedError
	
	get_path = get_data

class ProfileException(Exception):
	def __init__(self, err):	self.err = err
	def __str__(self): return str(self.err)
