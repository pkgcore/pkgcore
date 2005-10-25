# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: ebuild_package.py 2171 2005-10-25 14:35:50Z ferringb $

import os
from portage import package
from conditionals import DepSet
from portage.package.atom import atom
from digest import parse_digest
from portage.util.mappings import LazyValDict
from portage.restrictions.values import StrExactMatch
from portage.restrictions.packages import PackageRestriction
from portage.chksum.errors import MissingChksum
from portage.fetch.errors import UnknownMirror
from portage.fetch import fetchable, mirror
import const
import processor

# utility func.
def create_fetchable_from_uri(chksums, mirrors, uri):
	file = os.path.basename(uri)
	if file == uri:
		uri = []
	else:
		if uri.startswith("mirror://"):
			# mirror:// is 9 chars.
			tier, uri = uri[9:].split("/", 1)
			if tier not in mirrors:
				raise UnknownMirror(tier, uri)
			uri = mirror(uri, mirrors[tier])
			# XXX replace this with an iterable instead
		else:
			uri = [uri]
	if file not in chksums:
		raise MissingChksum(file)
	return fetchable(file, uri, chksums[file])


class EbuildPackage(package.metadata.package):
	immutable = False

	def __init__(self, cpv, parent, pull_path):
		super(EbuildPackage, self).__init__(cpv, parent)
		self.__dict__["_get_path"] = pull_path
	
	def __getattr__(self, key):
		val = None
		if key == "path":
			val = self._get_path(self)
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
			val = DepSet(self.data.get("DEPEND",""), atom)
		elif key == "rdepends":
			val = DepSet(self.data.get("RDEPEND","") + " " + self.data.get("PDEPEND", ""), atom)
		elif key == "fetchables":
			chksums = parse_digest(os.path.join(self.__dict__["_parent"]._base, self.category, self.package, "files",
				"digest-%s-%s" % (self.package, self.fullver)))
			val = DepSet(self.data["SRC_URI"], lambda x:create_fetchable_from_uri(chksums, self.__dict__["_parent"]._mirrors, x), operators={})
		elif key in ("license", "slot"):
			val = DepSet(self.data[key.upper()], str)
		elif key == "description":
			val = self.data["DESCRIPTION"]
		elif key == "keywords":
			val = self.data["KEYWORDS"].split()
		elif key == "eapi":
			try:
				val = int(self.data.get("EAPI", 0))
			except ValueError:
				if self.data["EAPI"] == '':
					val = 0
				else:
					val = const.unknown_eapi
			except KeyError:
				val = 0
		else:
			return super(EbuildPackage, self).__getattr__(key)
		self.__dict__[key] = val
		return val

	def _fetch_metadata(self):
		data = self._parent._get_metadata(self)
		doregen = False
		if data == None:
			doregen = True
		# got us a dict.  yay.
		if not doregen:
			if self._mtime_ != long(data.get("_mtime_", -1)):
				doregen = True
			elif data.get("_eclasses_") != None and not self._parent._ecache.is_eclass_data_valid(data["_eclasses_"]):
				doregen = True

		if doregen:
			# ah hell.
			data = self._parent._update_metadata(self)

		return data


class EbuildFactory(package.metadata.factory):
	child_class = EbuildPackage

	def __init__(self, parent, cachedb, eclass_cache, mirrors, *args,**kwargs):
		super(EbuildFactory, self).__init__(parent, *args,**kwargs)
		self._cache = cachedb
		self._ecache = eclass_cache
		self._mirrors = mirrors
		self._base = self._parent_repo.base

	def _get_metadata(self, pkg):
		if self._cache != None:
			try:
				return self._cache[pkg.cpvstr]
			except KeyError:
				pass
		return None

	def _update_metadata(self, pkg):

		ebp=processor.request_ebuild_processor()
		mydata = ebp.get_keys(pkg, self._ecache)
		processor.release_ebuild_processor(ebp)

		mydata["_mtime_"] = pkg._mtime_
		if mydata.get("INHERITED", False):
			mydata["_eclasses_"] = self._ecache.get_eclass_data(mydata["INHERITED"].split() )
			del mydata["INHERITED"]
		else:
			mydata["_eclasses_"] = {}

		if self._cache != None:
			self._cache[pkg.cpvstr] = mydata

		return mydata

	def _get_new_child_data(self, cpv):
		return ([self._parent_repo._get_ebuild_path], {})


def generate_new_factory(*a, **kw):
	return EbuildFactory(*a, **kw).new_package
