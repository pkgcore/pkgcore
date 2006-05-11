#!/usr/bin/python
import time, sys
from pkgcore.config import load_config
from pkgcore.package.metadata import MetadataException
c=load_config()
if len(sys.argv) == 1:
	attrs = ("depends", "rdepends", "provides", "license", "fetchables")
	print "no specific attrs specified, defaulting to",attrs
else:
	attrs = [x.lower() for x in sys.argv[1:]]
	for x in attrs:
		if x not in ("depends", "rdepends", "provides", "license", "fetchables", "slot",
			"keywords", "description"):
			print "'%s' isn't a valid attr to scan for" % x
			sys.exit(1)
start_time = time.time()
print "starting...\n"
for x in c.repo["rsync repo"]:
	for y in attrs:
		try:
			getattr(x, y)
			continue
		except MetadataException, m:
			print m
		except TypeError, e:
			print x,e
		print
print "finished in %.2f seconds" % (time.time() - start_time)
