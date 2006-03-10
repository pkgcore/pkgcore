# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2
# $Id: digest.py 2273 2005-11-10 00:22:02Z ferringb $

from portage.chksum.errors import ParseChksumError
def parse_digest(path, throw_errors=True):
	d = {}
	try:
		f = open(path)
		for line in f:
			l = line.split()
			if len(l) == 0:
				continue
			if len(l) != 4:
				if throw_errors:
					raise ParseChksumError(path, "line count was not 4, was %i: '%s'" % (len(l), line))
			#MD5 c08f3a71a51fff523d2cfa00f14fa939 diffball-0.6.2.tar.bz2 305567
			d[l[2]] = {l[0].lower():l[1], "size":long(l[3])}
		f.close()
	except (OSError, IOError, TypeError), e:
		raise ParseChksumError("failed parsing " + path, e)
	return d
