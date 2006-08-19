# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
binpkg tar utilities
"""
import os
from pkgcore.util.tar import TarFile
from pkgcore.fs.fs import fsFile, fsDir, fsSymlink, fsDev, fsFifo
from pkgcore.fs import contents
from pkgcore.util.mappings import OrderedDict
from pkgcore.interfaces.data_source import data_source
from pkgcore.util.currying import pre_curry

class tar_data_source(data_source):
	
	def get_fileobj(self):
		return self.data()

class TarContentsSet(contents.contentsSet):
	
	def __init__(self, initial=None, mutable=False):
		contents.contentsSet.__init__(self, mutable=True)
		self._dict = OrderedDict()
		if initial is not None:
			for x in initial:
				self.add(x)
		self.mutable = mutable


def converter(src_tar):
	psep = os.path.sep
	for member in src_tar:
		d = {"uid":member.uid, "gid":member.gid, "mtime":member.mtime, "mode":member.mode}
		location = psep + member.name.strip(psep)
		if member.isdir():
			if member.name.strip(psep) == ".":
				continue
			yield fsDir(location, **d)
		elif member.isreg():
			d["size"] = long(member.size)
			d["data_source"] = tar_data_source(pre_curry(src_tar.extractfile, member.name))
			yield fsFile(location, **d)
		elif member.issym():
			yield fsSymlink(location, member.linkname, **d)
		else:
			print "skipping",member

def generate_contents(path):
	t = TarFile.bz2open(path, mode="r")
	return TarContentsSet(converter(t), mutable=False)
