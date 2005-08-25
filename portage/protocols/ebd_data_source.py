# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id$

import os

class base(object):
	def get_data(self, arg):
		raise NotImplementedError
	get_path = get_data
	
class local_source(base):

	def get_path(self, arg):
		if os.path.exists(arg):
			return arg
		return False
		
	def get_data(self, arg):
		fp = self.get_path(arg)
		if fp == None:
			return None
		try:
			f = open(fp, "r")
			d = f.read()
			f.close()
			return d 
		except OSError:
			return None
