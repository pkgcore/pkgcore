# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2
# $Id: errors.py 2278 2005-11-10 00:25:26Z ferringb $

class TreeCorruption(Exception):
	def __init__(self, err):
		self.err = err
	def __str__(self):
		return "unexpected tree corruption: %s" % str(self.err)

class InitializationError(TreeCorruption):
	def __str__(self):
		return "initialization failed: %s" % str(self.err)
