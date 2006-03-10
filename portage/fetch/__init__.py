# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2
# $Id:$
from fetchable import fetchable
from itertools import imap

class mirror(object):
	__slots__ = ("uri", "mirrors")
	def __init__(self, uri, mirrors):
		self.uri = uri
		self.mirrors = mirrors

	def __iter__(self):
		return imap(lambda x: "%s/%s" % (x, self.uri), self.mirrors)

