#!/usr/bin/python
# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id:$

import portage.plugins
from portage.util.modules import load_attribute
import sys

def set(ptype, magic, version, namespace):
	load_attribute(namespace)
	# loaded.
	portage.plugins.register(ptype, magic, version, namespace, replace=True)

def cleanse(ptype, magic, version):
	portage.plugins.deregister(ptype, magic, version)
	
def get_list(ptype=None):
	return portage.plugins.query_plugins(ptype)

if __name__ == "__main__":
	args = sys.argv[1:]
	ret = 0
	if "-l" in args:
		args.pop(args.index("-l"))
		if len(args) == 0:
			args = [None]
		for x in args:
			print "querying %s" % str(x)
			try:
				print get_list(x)
			except Exception, e:
				print "caught exception %s querying" % e
				ret = 1
	elif "-s" in args:
		args.pop(args.index("-s"))
		if len(args) != 4:
			print "need 4 args- ptype magic version namespace"
			sys.exit(1)
		print "registering namespace(%s) as type(%s) constant(%s), ver(%s)" % (args[3], args[0], args[1], args[2])
		set(*args)
	elif "-r" in args:
		args.pop(args.index("-r"))
		if len(args) != 3:
			print "need 3 args- ptype magic version"
			sys.exit(1)
		print "deregistering type(%s) constant(%s) ver(%s)" % (args[0], args[1], args[2])
		cleanse(*args)
	else:
		if "--help" not in args:
			print "command required"
		print
		print "options available: -s, -r, -l"
		print "-s ptype magic ver namespace"
		print "-r ptype magic ver"
		print "-l [ptype]"
		print
		if "--help" not in args:
			sys.exit(1)
	sys.exit(0)
