# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.chksum.errors import ParseChksumError
def parse_digest(path, throw_errors=True):
	d = {}
	try:
		f = open(path, "r", 32384)
		for line in f:
			l = line.split()
			if not l:
				continue
			if len(l) != 4:
				if throw_errors:
					raise ParseChksumError(path, "line count was not 4, was %i: '%s'" % (len(l), line))
				continue

			#MD5 c08f3a71a51fff523d2cfa00f14fa939 diffball-0.6.2.tar.bz2 305567
			d.setdefault(l[2], {})[l[0].lower()] = l[1]
			if "size" not in d[l[2]]:
				d[l[2]]["size"] = long(l[3])
		f.close()
	except (OSError, IOError, TypeError), e:
		raise ParseChksumError("failed parsing " + path, e)
	return d
