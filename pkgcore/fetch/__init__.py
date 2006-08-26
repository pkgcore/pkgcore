# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
functionality related to downloading files
"""


class fetchable(object):

	"""class representing uri sources for a file and chksum information."""

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


class mirror(object):
	"""
	uri source representing a mirror tier
	"""
	__slots__ = ("uri", "mirrors", "mirror_name")
	def __init__(self, uri, mirrors, mirror_name):
		"""
		@param uri: the uri to try accessing per mirror server
		@param mirrors: list of hosts that comprise this mirror tier
		@param mirror_name: name of the mirror tier
		"""
		
		self.uri = uri
		self.mirrors = mirrors
		self.mirror_name = mirror_name

	def __iter__(self):
		return ("%s/%s" % (x, self.uri) for x in self.mirrors)

	def __str__(self):
		return "mirror://%s/%s" % (self.mirror_name, self.uri)

	def __len__(self):
		return len(self.mirrors)

	def __getitem__(self, idx):
		return "%s/%s" % (self.mirrors[idx], self.uri)
