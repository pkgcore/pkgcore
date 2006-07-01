# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
class representing uri sources for a file, and chksum information for the file
"""

class fetchable(object):
	__slots__ = ("filename", "uri", "chksums")

	def __init__(self, filename, uri=None, chksums=None):
		"""
		@param filename: filename...
		@param uri: either None (no uri), or a sequence of uri where the file is available
		@param chksums: either None (no chksum data), or a dict of chksum_type -> value for this file
		"""
		self.uri = uri
		if chksums is None:
			self.chksums = {}
		else:
			self.chksums = chksums
		self.filename = filename

	def __str__(self):
		return "('%s', '%s', (%s))" % (self.filename, self.uri, ', '.join(self.chksums))
