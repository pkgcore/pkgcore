# Copyright: 2005 Gentoo Foundation
# Author(s): Jeff Oliver (kaiserfro@yahoo.com)
# License: GPL2
# $Id: repository.py 1969 2005-09-04 07:38:17Z jstubbs $

from portage.config import load_config
from portage.repository import prototype, errors
from portage.package import metadata
from portage.package.cpv import CPV
from portage.package.atom import atom
from portage.ebuild.conditionals import DepSet
from portage.restrictions.packages import OrRestriction

import portage.vdb.repository


class tree(prototype.tree):

	def __init__(self, location, parent):
		super(tree,self).__init__()
		# XXX: It'd be much nicer to receive the parent vdb repo directly.
		# The following is too horrible to describe.
		# -- jstubbs
		parent = load_config().repo[parent]
		if not isinstance(parent, portage.vdb.repository):
			raise errors.InitializationError("parent must be a portage.vdb.repository repo" + str(type(parent)))
		self.parent = parent
		self._initialized = False
		self.package_class = factory(self).new_package

	def _grab_virtuals(self):
		self._virtuals = {}
		for pkg in self.parent:
			for virtual in DepSet(pkg.data["PROVIDE"], atom).evaluate_depset(pkg.data["USE"].split()):
				if virtual.category not in self._virtuals:
					self._virtuals[virtual.category] = {}
				if virtual.package not in self._virtuals[virtual.category]:
					self._virtuals[virtual.category][virtual.package] = {}
				if pkg.fullver not in self._virtuals[virtual.category][virtual.package]:
					self._virtuals[virtual.category][virtual.package][pkg.fullver] = OrRestriction(atom("="+str(pkg)))
				else:
					self._virtuals[virtual.category][virtual.package][pkg.fullver].add_restriction(atom("="+str(pkg)))
		for cat in self._virtuals:
			for pkg in self._virtuals[cat]:
				for ver in self._virtuals[cat][pkg]:
					self._virtuals[cat][pkg][ver] = OrRestriction(self._virtuals[cat][pkg][ver])
					self._virtuals[cat][pkg][ver].finalize()
		self._initialized = True

	def _fetch_metadata(self, pkg):
		if not self._initialized:
			self._grab_virtuals()
		return self._virtuals[pkg.category][pkg.package][pkg.fullver]

	def _get_categories(self, *optionalCategory):
		# return if optionalCategory is passed... cause it's not yet supported
		if len(optionalCategory):
			return {}

		if not self._initialized:
			self._grab_virtuals()

		return self._virtuals.keys()

	def _get_packages(self, category):
		if not self._initialized:
			self._grab_virtuals()

		return self._virtuals[category].keys()

	def _get_versions(self, catpkg):
		if not self._initialized:
			self._grab_virtuals()

		cat,pkg = catpkg.split("/")
		return self._virtuals[cat][pkg].keys()


class package(metadata.package):

	def __getattr__ (self, key):
		val = None
		if key == "rdepends":
			val = self.data
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
