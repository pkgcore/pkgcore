# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
functionality related to downloading files
"""

from fetchable import fetchable
from itertools import imap

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
