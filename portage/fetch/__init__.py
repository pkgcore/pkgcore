# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
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

