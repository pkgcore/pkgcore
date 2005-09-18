# Copyright: 2005 Gentoo Foundation
# Author(s): Jeff Oliver (kaiserfro@yahoo.com)
# License: GPL2
# $Id$

import os
from portage.package import metadata
from portage.ebuild.conditionals import DepSet
from portage.package.atom import atom
from portage.util.mappings import LazyValDict
from contents import contentsFile

class package(metadata.package):

	def __getattr__ (self, key):
		val = None
		if key == "path":
			val = os.path.join(self.__dict__["_parent"].base, self.category, \
				"%s-%s" % (self.package, self.fullver))
		elif key == "_mtime_":
			#XXX wrap this.
			val = long(os.stat(self.path).st_mtime)
		elif key == "P":
			val = self.package + "-" + self.version
		elif key == "PN":
			val = self.package
		elif key == "PR":
			val = "-r"+str(self.revision)
		elif key == "depends":
			# XXX: vdb deps need to flattened and the current dep scheme needs to be supported
			# or migrated somehow. Doing it here for the time being shouldn't hurt anything though
			# (except perhaps speed). Dropping bdepend as well as this is not for certain yet even
			# if the idea behind it is.
			# -- jstubbs
			val = DepSet(self.data["DEPEND"], atom).evaluate_depset(self.data["USE"].split())
		elif key == "rdepends":
			val = DepSet(self.data["RDEPEND"]+" "+self.data["PDEPEND"], atom).evaluate_depset(self.data["USE"].split())
		elif key in ("license", "slot"):
			val = DepSet(self.data[key.upper()], str)

		elif key == "fetchables":
			val = DepSet(self.data.get("SRC_URI", ""), str, operators={})
		elif key == "description":
			val = self.data.get("DESCRIPTION", "")
		elif key == "contents":
			val = contentsFile(os.path.join(self.path, "CONTENTS"))
#		elif key == "keywords":
#			val = self.data["KEYWORDS"].split()
		else:
			return super(package, self).__getattr__(key)
		self.__dict__[key] = val
		return val

	def _fetch_metadata(self):
		data = self._parent._get_metadata(self)
		doregen = False
		if data == None:
			doregen = True

#		if doregen:
			# ah hell.
#			data = self._parent._update_metadata(self)

		return data


class factory(metadata.factory):
	child_class = package

	def __init__(self, parent, *args, **kwargs):
		super(factory, self).__init__(parent, *args, **kwargs)
		self.base = self._parent_repo.base

	def _get_metadata(self, pkg):
		path = os.path.join(self.base, pkg.category, "%s-%s" % (pkg.package, pkg.fullver))
		try:
			keys = filter(lambda x: x.isupper(), os.listdir(path))
		except OSError:
			return None

		def load_data(key):
			try:
				f = open(os.path.join(path, key))
			except OSError:
				return None
			data = f.read()
			f.close()
			return data.strip()

		return LazyValDict(keys, load_data)

