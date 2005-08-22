# parseuri.py; parses a SYNC uri, returning protocol/host_uri
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#$Header$


#sanitize this to use listdir
#~harring

import portage_const

def parseSyncUri(uri):
	"""parse a SYNC uri, returning a tuple of protocol,host_uri"""
	u=uri.lower()
	if u.startswith("rsync") or len(u) == 0:
		if len(u) <= 5:
			return ('rsync',portage_const.RSYNC_HOST)
		return ('rsync',u[8:])
	elif u.startswith("cvs://"):
		u=u[6:]
		return ('cvs',u)
	elif u.startswith("snapshot"):
		if len(u)==8:
			# the caller gets to randomly crapshoot a mirror for it.
			return ('snapshot',None)
		return ('snapshot',u[9:])
	else:
		return (None,None)
