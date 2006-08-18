# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2


"""
default chksum handlers implementation- sha1, sha256, rmd160, and md5
"""

from pkgcore.util.currying import pre_curry
from pkgcore.util import modules
blocksize = 32768

def loop_over_file(obj, filename):
	wipeit = isinstance(filename, basestring)
	if wipeit:
		f = open(filename, 'rb', blocksize * 2)
	else:
		f = filename
		# reposition to start
		f.seek(0, 0)
	try:
		data = f.read(blocksize)
		size = 0L
		sum = obj.new()
		while data:
			sum.update(data)
			size = size + len(data)
			data = f.read(blocksize)

		return sum.hexdigest()
	finally:
		if wipeit:
			f.close()

import md5
try:
	import fchksum
	def md5hash(filename):
		if isinstance(filename, basestring):
			return fchksum.fmd5t(filename)[0]
		return loop_over_file(md5, filename)

except ImportError:
	import md5
	md5hash = pre_curry(loop_over_file, md5)

chksum_types = {"md5":md5hash}

# expand this to load all available at some point
for k,v in (("sha1", "SHA"), ("sha256", "SHA256"), ("rmd160", "RIPEMD")):
	try:
		chksum_types[k] = pre_curry(loop_over_file, modules.load_module("Crypto.Hash.%s" % v))
	except modules.FailedImport:
		pass
del k, v

if "sha1" not in chksum_types:
	import sha
	chksum_types["sha1"] = pre_curry(loop_over_file, sha)
