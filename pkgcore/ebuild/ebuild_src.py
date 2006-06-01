# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os, operator, errno, weakref
from pkgcore.package import metadata
from pkgcore.ebuild import conditionals
from pkgcore.package.atom import atom
from digest import parse_digest
from pkgcore.util.mappings import IndeterminantDict
from pkgcore.util.currying import post_curry, alias_class_method
from pkgcore.restrictions.packages import AndRestriction
from pkgcore.restrictions import boolean
from pkgcore.chksum.errors import MissingChksum
from pkgcore.fetch.errors import UnknownMirror
from pkgcore.fetch import fetchable, mirror
from pkgcore.ebuild import const, processor
from pkgcore.util.demandload import demandload
demandload(globals(), "pkgcore.util.xml:etree")

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

def generate_depset(s, c, *keys, **kwds):
	if kwds.pop("non_package_type", False):
		kwds["operators"] = {"||":boolean.OrRestriction, "":boolean.AndRestriction}
	try:
		return conditionals.DepSet(" ".join([s.data.get(x.upper(), "") for x in keys]), c, **kwds)
	except conditionals.ParseError, p:
		raise metadata.MetadataException(s, str(keys), str(p))

def generate_providers(self):
	rdep = AndRestriction(self.versioned_atom, finalize=True)
	func = post_curry(virtual_ebuild, self._parent, self, {"rdepends":rdep})
	# re-enable license at some point.
	#, "license":self.license})

	try:
		return conditionals.DepSet(self.data.get("PROVIDE", ""), virtual_ebuild, 
			element_func=func, 
			operators={"||":boolean.OrRestriction,"":boolean.AndRestriction})

	except conditionals.ParseError, p:
		raise metadata.MetadataException(self, "provide", str(p))

def generate_fetchables(self):
	chksums = parse_digest(os.path.join(os.path.dirname(self.path), "files", \
		"digest-%s-%s" % (self.package, self.fullver)))
	try:
		return conditionals.DepSet(self.data["SRC_URI"], fetchable, operators={}, 
			element_func=lambda x:create_fetchable_from_uri(chksums, self._mirrors, x))
	except conditionals.ParseError, p:
		raise metadata.MetadataException(self, "src_uri", str(p))

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

def pull_metadata_xml(self, attr):
	if self._pkg_metadata_shared[0] is None:
		try:
			tree = etree.parse(os.path.join(os.path.dirname(self.path), "metadata.xml"))
			maintainers = []
			for x in tree.findall("maintainer"):
				name = email = None
				for e in x:
					if e.tag == "name":
						name = e.text
					elif e.tag == "email":
						email = e.text
				if name is not None:
					if email is not None:
						maintainers.append("%s <%s>" % (name, email))
					else:
						maintainers.append(name)
				elif email is not None:
					maintainers.append(email)

			self._pkg_metadata_shared[0] = tuple(maintainers)
			self._pkg_metadata_shared[1] = tuple(str(x.text) for x in tree.findall("herd"))

		except IOError, i:
			if i.errno != 22:
				raise
			self._pkg_metadata_shared[0] = ()
			self._pkg_metadata_shared[1] = ()
	self.__dict__["maintainers"] = self._pkg_metadata_shared[0]
	self.__dict__["herds"] = self._pkg_metadata_shared[1]
	return self.__dict__[attr]


class package(metadata.package):
	immutable = False
	allow_regen = True
	tracked_attributes = ["PF", "depends", "rdepends", "provides", 	"license",
		"slot", "keywords", "eapi", "restrict"]

	_config_wrappables = dict((x, alias_class_method("evaluate_depset")) 
		for x in ["depends", "rdepends", "fetchables", "license", "src_uri", 
		"license", "provides"])

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
	_get_attr["PR"] = lambda s: "r"+str(s.revision is not None and s.revision or 0)
	_get_attr["provides"] = generate_providers
	_get_attr["depends"] = post_curry(generate_depset, atom, "depend")
	_get_attr["rdepends"] = post_curry(generate_depset, atom, "rdepend", "pdepend")
	_get_attr["license"] = post_curry(generate_depset, str, "license", non_package_type=True)
	_get_attr["slot"] = lambda s: s.data.get("SLOT", "0").strip()
	_get_attr["fetchables"] = generate_fetchables
	_get_attr["description"] = lambda s:s.data.get("DESCRIPTION", "").strip()
	_get_attr["keywords"] = lambda s:s.data.get("KEYWORDS", "").split()
	_get_attr["restrict"] = lambda s:s.data.get("RESTRICT", "").split()
	_get_attr["eapi"] = generate_eapi
	_get_attr["iuse"] = lambda s:s.data.get("IUSE", "").split()
	_get_attr["herds"] = lambda s:pull_metadata_xml(s, "herds")
	_get_attr["maintainers"] = lambda s:pull_metadata_xml(s, "maintainers")

	def _fetch_metadata(self):
		data = self._parent._get_metadata(self)
		if not self.allow_regen:
			return data
		if data is None:
			doregen = True
		elif self._mtime_ != long(data.get("_mtime_", -1)):
			doregen = True
		elif data.get("_eclasses_") is not None and not self._parent._ecache.is_eclass_data_valid(data["_eclasses_"]):
			doregen = True
		else:
			return data
		# ah hell.
		return self._parent._update_metadata(self)


class package_factory(metadata.factory):
	child_class = package

	def __init__(self, parent, cachedb, eclass_cache, mirrors, *args, **kwargs):
		super(package_factory, self).__init__(parent, *args, **kwargs)
		self._cache = cachedb
		self._ecache = eclass_cache
		self._mirrors = mirrors
		self._weak_pkglevel_cache = weakref.WeakValueDictionary()

	def _get_metadata(self, pkg):
		if self._cache is not None:
			try:
				return self._cache[pkg.cpvstr]
			except KeyError:
				pass
		return None

	def _update_metadata(self, pkg):
		ebp = processor.request_ebuild_processor()
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

	def new_package(self, cpv):
		inst = metadata.factory.new_package(self, cpv)
		if inst.key not in self._weak_pkglevel_cache:
			o = ThrowAwayNameSpace([None, None])
			self._weak_pkglevel_cache[inst.key] = o
		else:
			o = self._weak_pkglevel_cache[inst.key]
		inst.__dict__["_pkg_metadata_shared"] = o
		return inst


class ThrowAwayNameSpace(object):
	"""used for weakref passing data only"""
	def __init__(self, val):
		self._val = val
	
	def __getitem__(self, index):
		return self._val[index]
	
	def __setitem__(self, slice, val):
		self._val[slice] = val


def generate_new_factory(*a, **kw):
	return package_factory(*a, **kw).new_package
	__slots__ = ("__weak__", "herds", "maintainers")


class virtual_ebuild(metadata.package):

	def __init__(self, cpv, parent_repository, pkg, data):
		self.__dict__["data"] = IndeterminantDict(lambda *a: str(), data)
		self.__dict__["_orig_data"] = data
		self.__dict__["actual_pkg"] = pkg
		state = set(self.__dict__.keys())
		# hack. :)
		metadata.package.__init__(self, cpv, parent_repository)
		if not self.version:
			for x in self.__dict__.keys():
				if x not in state:
					del self.__dict__[x]
			metadata.package.__init__(self, cpv+"-"+pkg.fullver, parent_repository)
			assert self.version

	def __getattr__(self, attr):
		if attr in self._orig_data:
			return self._orig_data[attr]
		return metadata.package.__getattr__(self, attr)

	_get_attr = package._get_attr.copy()
