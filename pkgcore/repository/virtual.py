# Copyright: 2005 Jason Stubbs <jstubbs@gentoo.org>
# License: GPL2

from pkgcore.restrictions.packages import OrRestriction
from pkgcore.repository import prototype
from pkgcore.package import metadata

class tree(prototype.tree):

	def __init__(self, grab_virtuals_func):
		super(tree,self).__init__()
		if not callable(grab_virtuals_func):
			raise TypeError("grab_virtuals_func must be a callable")
		self._grab_virtuals = grab_virtuals_func
		self.package_class = factory(self).new_package
		self._virtuals = None

	def _fetch_metadata(self, pkg):
		if self._grab_virtuals is not None:
			self._virtuals = self._grab_virtuals()
			self._grab_virtuals = None
		return self._virtuals[pkg.package][pkg.fullver]

	def _get_categories(self, *optionalCategory):
		# return if optionalCategory is passed... cause it's not yet supported
		if optionalCategory:
			return ()
		return ("virtual",)

	def _get_packages(self, category):
		if self._grab_virtuals is not None:
			self._virtuals = self._grab_virtuals()
			self._grab_virtuals = None

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
		elif key == "provides":
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
