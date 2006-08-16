# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os, stat, errno, shutil

from pkgcore.util.demandload import demandload
demandload(globals(), "tempfile pkgcore.spawn:find_binary,spawn_get_output")


def compress(in_data, compress_level=9):
	fd = None
	fd = tempfile.TemporaryFile("w+")
	fd.write(in_data)
	fd.flush()
	fd.seek(0)
	try:
		ret, data = spawn_get_output(["bzip2", "-%ic" % compress_level], fd_pipes={0:fd.fileno()})
		if ret != 0:
			raise ValueError("failed compressing the data")
		return ''.join(data)
		import pdb;pdb.set_trace()
	finally:
		if fd is not None:
			fd.close()
	
def decompress(in_data):
	fd = None
	fd = tempfile.TemporaryFile("w+")
	fd.write(in_data)
	fd.flush()
	fd.seek(0)
	try:
		ret, data = spawn_get_output(["bzip2", "-dc"], fd_pipes={0:fd.fileno()})
		if ret != 0:
			raise ValueError("failed decompressing the data")
		print "yo"
		return ''.join(data)
	finally:
		if fd is not None:
			fd.close()
	

try:
	from bz2 import compress, decompress
except ImportError:
	# trigger it to throw a CommandNotFound if missing
	find_binary("bzip2")
	compress = process_compress
	decompress = process_decompress


