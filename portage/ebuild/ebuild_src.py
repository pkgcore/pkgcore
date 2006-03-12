# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os
from portage.package import metadata
from conditionals import DepSet
from portage.package.atom import atom
from digest import parse_digest
from portage.util.mappings import LazyValDict
from portage.util.currying import post_curry
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

def generate_depset(s, c, *keys):
	return DepSet(" ".join([s.data.get(x.upper(),"") for x in keys]), c)

def generate_fetchables(self):
	chksums = parse_digest(os.path.join(os.path.dirname(self.path), "files", \
		"digest-%s-%s" % (self.package, self.fullver)))
	return DepSet(self.data["SRC_URI"], lambda x:create_fetchable_from_uri(chksums, self._mirrors, x), operators={})

def generate_eapi(self):
	try:
		val = int(self.data.get("EAPI", 0))
	except ValueError:
		if self.data["EAPI"] == '':
			val = 0
		else:
			val = const.unknown_eapi
	except KeyError:
		val = 0
	return val

class package(metadata.package):
	immutable = False
	allow_regen = True
	tracked_attributes=["PF", "depends","provides","rdepends","license","slot","keywords",
	"eapi", "restrict"]

	def __init__(self, cpv, parent, pull_path, mirrors=None):
		super(package, self).__init__(cpv, parent)
		self.__dict__["_get_path"] = pull_path
		if mirrors is None:
			mirrors = {}
		self.__dict__["_mirrors"] = mirrors

	_convert_data = {}
	_convert_data["path"] = lambda s:s._get_path(s)
	_convert_data["_mtime_"] = lambda s: long(os.stat(s.path).st_mtime)
	_convert_data["P"] = lambda s: s.package+"-"+s.fullver
	_convert_data["PF"] = lambda s: s.package
	_convert_data["PN"] = lambda s: s.package
	_convert_data["PR"] = lambda s: "-r"+str(s.revision)
	_convert_data.update((x, post_curry(generate_depset, atom, x.rstrip("s"),)) for x in ("depends", "provides"))
	_convert_data["rdepends"] = post_curry(generate_depset, atom, "rdepends", "pdepends")
	_convert_data.update((x, post_curry(generate_depset, str, x)) for x in ("license", "slot"))
	_convert_data["fetchables"] = generate_fetchables
	_convert_data["description"] = lambda s:s.data["DESCRIPTION"]
	_convert_data["keywords"] = lambda s:s.data["KEYWORDS"].split()
	_convert_data["restrict"] = lambda s:s.data["RESTRICT"].split()
	_convert_data["eapi"] = generate_eapi

	def __getattr__(self, key):
		val = None
		if key in self._convert_data:
			val = self._convert_data[key](self)
		else:
			return super(package, self).__getattr__(key)
		self.__dict__[key] = val
		return val

	def _fetch_metadata(self):
		data = self._parent._get_metadata(self)
		if not self.allow_regen:
			return data
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


class package_factory(metadata.factory):
	child_class = package

	def __init__(self, parent, cachedb, eclass_cache, mirrors, *args,**kwargs):
		super(package_factory, self).__init__(parent, *args,**kwargs)
		self._cache = cachedb
		self._ecache = eclass_cache
		self._mirrors = mirrors

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
		return ([self._parent_repo._get_ebuild_path], {"mirrors":self._mirrors})


def generate_new_factory(*a, **kw):
	return package_factory(*a, **kw).new_package

