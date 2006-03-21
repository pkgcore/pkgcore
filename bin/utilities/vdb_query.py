#!/usr/bin/python
from pkgcore.config import load_config
from pkgcore.package.atom import atom
import sys

v=load_config().domain["livefs domain"].vdb[0]
for x in sys.argv[1:]:
	print "atom=%s" % x
	for y in v.itermatch(atom(x)):
		print y
	print
