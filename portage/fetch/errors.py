# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id:$

class base(Exception):
	pass

class distdirPerms(base):
	def __init__(self, distdir, required):	self.distdir, self.required = distdir, required
	def __str__(self):
		return "distdir '%s' required fs attributes weren't enforcable: %s" % (self.distdir, self.required)

class UnmodifiableFile(base):
	def __init__(self, file, extra=''):	self.file = file
	def __str__(self): 			return "Unable to update file %s, unmodifiable %s" % (self.file, self.extra)

class UnknownMirror(base):
	def __init__(self, host, uri): self.host, self.uri = host, uri
	def __str__(self):	return "uri mirror://%s/%s is has no known mirror tier" % (self.host, self.uri)

class RequiredChksumDataMissing(base):
	def __init__(self, fetchable, chksum):	self.fetchable, self.missing_chksum = fetchable, chksum
	def __str__(self):
		return "chksum %s was configured as required, but the data is missing from fetchable '%s'" (self.chksum, self.fetchable)
