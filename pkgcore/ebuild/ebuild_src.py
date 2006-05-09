# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os, operator
from pkgcore.package import metadata
from pkgcore.ebuild import conditionals
from pkgcore.package.atom import atom
from digest import parse_digest
from pkgcore.util.mappings import LazyValDict, IndeterminantDict
from pkgcore.util.currying import post_curry, alias_class_method
from pkgcore.restrictions.values import StrExactMatch
from pkgcore.restrictions.packages import PackageRestriction, AndRestriction
from pkgcore.chksum.errors import MissingChksum
from pkgcore.fetch.errors import UnknownMirror
from pkgcore.fetch import fetchable, mirror
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
	return conditionals.DepSet(" ".join([s.data.get(x.upper(),"") for x in keys]), c)

def generate_providers(self):
	rdep = AndRestriction(self.versioned_atom, finalize=True)
	func = post_curry(virtual_ebuild, self._parent, self, {"rdepends":rdep})
	# re-enable license at some point.
	#, "license":self.license})
	return conditionals.DepSet(self.data.get("PROVIDE", ""), virtual_ebuild, element_func=func)

def generate_fetchables(self):
	chksums = parse_digest(os.path.join(os.path.dirname(self.path), "files", \
		"digest-%s-%s" % (self.package, self.fullver)))
	return conditionals.DepSet(self.data["SRC_URI"], lambda x:
		create_fetchable_from_uri(chksums, self._mirrors, x), operators={})

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
	tracked_attributes=["PF", "depends", "rdepends", "provides","license", "slot", "keywords",
		"eapi", "restrict"]

	_config_wrappables = dict((x, alias_class_method("evaluate_depset")) for x in
		["depends","rdepends", "fetchables", "license", "slot", "src_uri", "license"])

	def __init__(self, cpv, parent, pull_path, mirrors=None):
		super(package, self).__init__(cpv, parent)
		self.__dict__["_get_path"] = pull_path
		if mirrors is None:
			mirrors = {}
		self.__dict__["_mirrors"] = mirrors

	_get_attr = dict(metadata.package._get_attr)
	_get_attr["path"] = lambda s:s._get_path(s)
	_get_attr["_mtime_"] = lambda s: long(os.stat(s.path).st_mtime)
	_get_attr["P"] = lambda s: s.package+"-"+s.version
	_get_attr["PF"] = lambda s: s.package+"-"+s.fullver
	_get_attr["PN"] = operator.attrgetter("package")
	_get_attr["PR"] = lambda s: "-r"+str(s.revision is not None and s.revision or 0)
#	_get_attr["provides"] = post_curry(generate_depset, atom, "provide")
	_get_attr["provides"] = generate_providers
	_get_attr["depends"] = post_curry(generate_depset, atom, "depend")
	_get_attr["rdepends"] = post_curry(generate_depset, atom, "rdepend", "pdepend")
	_get_attr.update((x, post_curry(generate_depset, str, x)) for x in ("license", "slot"))
	_get_attr["fetchables"] = generate_fetchables
	_get_attr["description"] = lambda s:s.data.get("DESCRIPTION", "")
	_get_attr["keywords"] = lambda s:s.data.get("KEYWORDS", "").split()
	_get_attr["restrict"] = lambda s:s.data.get("RESTRICT", "").split()
	_get_attr["eapi"] = generate_eapi

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


class virtual_ebuild(metadata.package):

	def __init__(self, cpv, parent_repository, pkg, data):
		self.__dict__["data"] = IndeterminantDict(lambda *a: str(), data)
		self.__dict__["_orig_data"] = data
		self.__dict__["actual_pkg"] = pkg
		metadata.package.__init__(self, cpv, parent_repository)

	def __getattr__(self, attr):
		if attr in self._orig_data:
			return self._orig_data[attr]
		return metadata.package.__getattr__(self, attr)

	_get_attr = package._get_attr.copy()
