#!/usr/bin/python
# Copyright: 2005-2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import pkgcore.plugins
from pkgcore.util.modules import load_attribute
import sys

def set(ptype, magic, version, namespace):
	load_attribute(namespace)
	# loaded.
	pkgcore.plugins.register(ptype, magic, version, namespace, replace=True)

def cleanse(ptype, magic, version):
	pkgcore.plugins.deregister(ptype, magic, version)

def get_list(ptype=None):
	return pkgcore.plugins.query_plugins(ptype)

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
				i = get_list(x).items()
				if x is not None:
					i = [(x, dict(i))]
				for k,v in i:
					print
					try:
						l = max(len(y) for y in v.keys()) + 4
						print "%s => " % k
						for y in v.keys():
							print "%s:    %s, %s" % (y.rjust(l), v[y]["namespace"], v[y]["version"])
					except ValueError:
						print "%s => no plugins found" % k
				print
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
	elif "-p" in args:
		args.pop(args.index("-p"))
		if len(args) != 0:
			print "no args allowed currently"
			sys.exit(1)
		for ptype, v in get_list(None).iteritems():
			for magic, vals in v.iteritems():
				print "%s -s %s %s %s %s" % (sys.argv[0], ptype, magic, vals["version"], vals["namespace"])
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
