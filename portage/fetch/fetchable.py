# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id:$

class fetchable(object):
	__slots__ = ("filename", "uri", "chksums")

	def __init__(self, filename, uri=None, chksums=None):
		self.uri = uri
		if chksums is None:
			self.chksums = {}
		else:
			self.chksums = chksums
		self.filename = filename

	def __str__(self):
		return "('%s', '%s', (%s))" % (self.filename, self.uri, ', '.join(self.chksums.keys()))
