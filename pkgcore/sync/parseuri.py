# parseuri.py; parses a SYNC uri, returning protocol/host_uri
# Copyright 2004-2006 Brian Harring <ferringb@gmail.com>
# Distributed under the terms of the GNU General Public License v2

"""WARNING, NEEDS WORK"""

#sanitize this to use listdir
#~harring

from pkgcore.const impor tRSYNC_HOST

def parseSyncUri(uri):
	"""parse a SYNC uri, returning a tuple of protocol,host_uri"""
	u = uri.lower()
	if u.startswith("rsync") or not u:
		if len(u) <= 5:
			return ('rsync', RSYNC_HOST)
		return ('rsync', u[8:])
	elif u.startswith("cvs://"):
		u = u[6:]
		return ('cvs', u)
	elif u.startswith("snapshot"):
		if len(u) == 8:
			# the caller gets to randomly crapshoot a mirror for it.
			return ('snapshot', None)
		return ('snapshot', u[9:])
	else:
		return (None, None)
