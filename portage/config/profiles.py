# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

class base(object):
	pass

class ProfileException(Exception):
	def __init__(self, err):	self.err = err
	def __str__(self): return str(self.err)
