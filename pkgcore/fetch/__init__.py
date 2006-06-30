# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2
from fetchable import fetchable
from itertools import imap

class mirror(object):
	__slots__ = ("uri", "mirrors", "mirror_name")
	def __init__(self, uri, mirrors, mirror_name):
		self.uri = uri
		self.mirrors = mirrors
		self.mirror_name = mirror_name

	def __iter__(self):
		return ("%s/%s" % (x, self.uri) for x in self.mirrors)

	def __str__(self):
		return "mirror://%s/%s" % (self.mirror_name, self.uri)
