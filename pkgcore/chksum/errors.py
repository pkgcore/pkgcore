# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
exceptions thrown by chksum subsystem
"""

class base(Exception):
	pass

class MissingChksum(base):

	def __init__(self, file):
		self.file = file

	def __str__(self):
		return "Missing chksum for file '%s'" % self.file

class ParseChksumError(base):
	def __init__(self, filename, error):
		self.file, self.error = filename, error

	def __str__(self):
		return "Failed parsing %s chksum due to %s" % (self.file, self.error)
