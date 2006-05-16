#!/usr/bin/python

import sys, time
from pkgcore.restrictions import packages, values
from pkgcore.config import load_config
from pkgcore.fs.util import normpath

if __name__ == "__main__":
	if len(sys.argv) == 1 or "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
		print "need at least one arg, file to find the owner of"
		print "Multiple args are further restrictions on a match- pkg must own all of the files"
		sys.exit(2)
	repo = load_config().domain["livefs domain"].vdb[0]
	restrict = packages.PackageRestriction("contents", values.ContainmentMatch(
		*[normpath(x) for x in sys.argv[1:]]))
	start_time = time.time()
	count = 0 
	print "query- %s" % restrict
	for pkg in repo.itermatch(restrict):
		print "pkg: %s" % (pkg)
		count += 1
	print "found %i matches in %.2f seconds" % (count, time.time() - start_time)
	if count:
		sys.exit(0)
	sys.exit(1)
