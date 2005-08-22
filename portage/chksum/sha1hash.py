# Copyright: 2004-2005 Gentoo Foundation
# License: GPL2
# $Header$

import sha

def sha1hash(filename, chksum):
	f = open(filename, 'rb')
	blocksize=32768
	data = f.read(blocksize)
	size = 0L
	sum = sha.new()
	while data:
		sum.update(data)
		size = size + len(data)
		data = f.read(blocksize)
	f.close()

	return sum.hexdigest() == chksum

chksum_types = (("sha1", sha1hash),)
