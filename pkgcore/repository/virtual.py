# Copyright: 2005 Jason Stubbs <jstubbs@gentoo.org>
# License: GPL2

"""
virtual repository, pkgs generated via callable
"""

from pkgcore.repository import prototype
from pkgcore.package import virtual

class tree(prototype.tree):

	def __init__(self, grab_virtuals_func, livefs=False):
		"""
		@param grab_virtuals_func: callable to get a package -> versions mapping
		@param livefs: is this a livefs repository?
		"""
		super(tree,self).__init__()
		self.livefs = livefs
		if not callable(grab_virtuals_func):
			if not hasattr(grab_virtuals_func, "__getitem__"):
				raise TypeError("grab_virtuals_func must be a callable")
			else:
				self._virtuals = grab_virtuals_func
				self._grab_virtuals = None
		else:
			self._grab_virtuals = grab_virtuals_func
			self._virtuals = None
		self.package_class = virtual.factory(self).new_package

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
			return tuple(self._virtuals.iterkeys())
		raise KeyError("no %s category for this repository" % category)

	def _get_versions(self, catpkg):
		cat,pkg = catpkg.rsplit("/", 1)
		if cat == "virtual":
			return tuple(self._virtuals[pkg].iterkeys())
		raise KeyError("no '%s' package in this repository" % catpkg)
