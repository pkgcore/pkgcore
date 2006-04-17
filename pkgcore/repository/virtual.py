# Copyright: 2005 Jason Stubbs <jstubbs@gentoo.org>
# License: GPL2

from pkgcore.config import load_config
from pkgcore.repository import prototype, errors
from pkgcore.package import metadata
from pkgcore.package.cpv import CPV
from pkgcore.package.atom import atom
from pkgcore.ebuild.conditionals import DepSet
from pkgcore.restrictions.packages import OrRestriction

from pkgcore.vdb import ondisk

class tree(prototype.tree):

	def __init__(self, parent):
		super(tree,self).__init__()
		if not isinstance(parent, ondisk.tree):
			raise errors.InitializationError("parent must be a pkgcore.vdb.ondisk repo" + str(type(parent)))
		self.parent = parent
		self.package_class = factory(self).new_package
		self._virtuals = None

	def _grab_virtuals(self):
		self._virtuals = {}
		for pkg in self.parent:
			for virtual in pkg.provides.evaluate_depset(pkg.use):
				self._virtuals.setdefault(virtual.package, {}).setdefault(pkg.fullver, []).append(pkg)

		for pkg_dict in self._virtuals.itervalues():
			for full_ver, rdep_atoms in pkg_dict.iteritems():
				if len(rdep_atoms) == 1:
					pkg_dict[full_ver] = atom("=%s" % rdep_atoms[0])
				else:
					pkg_dict[full_ver] = OrRestriction(finalize=True, *[atom("=%s" % x) for x in rdep_atoms])

	def _fetch_metadata(self, pkg):
		if self._virtuals is None:
			self._grab_virtuals()
		return self._virtuals[pkg.package][pkg.fullver]

	def _get_categories(self, *optionalCategory):
		# return if optionalCategory is passed... cause it's not yet supported
		if optionalCategory:
			return ()
		return ("virtual",)

	def _get_packages(self, category):
		if self._virtuals is None:
			self._grab_virtuals()

		if category == "virtual":
			return self._virtuals.keys()
		raise KeyError("no %s category for this repository" % category)

	def _get_versions(self, catpkg):
		cat,pkg = catpkg.split("/")
		if cat == "virtual":
			return self._virtuals[pkg].keys()
		raise KeyError("no '%s' package in this repository" % catpkg)


class package(metadata.package):

	def __getattr__ (self, key):
		val = None
		if key == "rdepends":
			val = self.data
		elif key == "depends":
			val = OrRestriction()
		elif key == "metapkg":
			val = True
		else:
			return super(package, self).__getattr__(key)
		self.__dict__[key] = val
		return val

	def _fetch_metadata(self):
		data = self._parent._parent_repo._fetch_metadata(self)
		return data


class factory(metadata.factory):
	child_class = package

	def __init__(self, parent, *args, **kwargs):
		super(factory, self).__init__(parent, *args, **kwargs)
