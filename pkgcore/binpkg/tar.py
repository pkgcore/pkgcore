# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.tar import TarFile
from pkgcore.fs.fs import fsFile, fsDir, fsSymLink, fsDev, fsFifo
from pkgcore.fs.contents import contentsSet

def generate_contents(path):
	t = TarFile.bz2open(path, mode="r")
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
	return contentsSet((converter(x) for x in t.getmembers()), frozen=True)
