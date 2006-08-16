# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
binpkg tar utilities
"""

from pkgcore.util.tar import TarFile
from pkgcore.fs.fs import fsFile, fsDir, fsSymLink, fsDev, fsFifo
from pkgcore.fs import contents
from pkgcore.util.mappings import OrderedDict

class TarContentsSet(contents.contentsSet):
	
	def __init__(self, initial=None, frozen=False):
		contents.contentsSet.__init__(self)
		self._dict = OrderedDict()
		if initial is not None:
			for x in initial:
				self.add(x)
		self.frozen = frozen


def converter(member):
	d = {"uid":member.uid, "gid":member.gid, "mtime":member.mtime, "mode":member.mode}
	location = member.name
	if member.isdir():
		return fsDir(location, **d)
	elif member.isreg():
		d["size"] = long(member.size)
		return fsFile(location, **d)
	elif member.issym():
		return fsSymLink(location, member.linkname, **d)
	else:
		print "skipping",member

def generate_contents(path):
	t = TarFile.bz2open(path, mode="r")
	return TarContentsSet((converter(x) for x in t), frozen=True)
