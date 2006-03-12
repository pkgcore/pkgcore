# Copyright: 2005 Jason Stubbs <jstubbs@gentoo.org>
# License: GPL2

from portage.config import load_config
from portage.repository import prototype, errors
from portage.package import metadata
from portage.package.cpv import CPV
from portage.package.atom import atom
from portage.ebuild.conditionals import DepSet
from portage.restrictions.packages import OrRestriction

import repository

class tree(prototype.tree):

	def __init__(self, parent):
		super(tree,self).__init__()
		if not isinstance(parent, repository.tree):
			raise errors.InitializationError("parent must be a portage.vdb.repository repo" + str(type(parent)))
		self.parent = parent
		self.package_class = factory(self).new_package
		self._virtuals = None

	def _grab_virtuals(self):
		self._virtuals = {}
		for pkg in self.parent:
			try:
				for virtual in DepSet(pkg.data["PROVIDE"], atom).evaluate_depset(pkg.data["USE"].split()):
					if virtual.package not in self._virtuals:
						self._virtuals[virtual.package] = {pkg.fullver:OrRestriction(atom("="+str(pkg)))}
					elif not pkg.fullver in self._virtuals[virtual.package]:
						self._virtuals[virtual.package][pkg.fullver] = OrRestriction(atom("="+str(pkg)))
					else:
						self._virtuals[virtual.package][pkg.fullver].add_restriction(atom("="+str(pkg)))
			except KeyError:
				pass

		for pkg in self._virtuals:
			map(lambda x: self._virtuals[pkg][x].finalize(), self._virtuals[pkg].keys())

	def _fetch_metadata(self, pkg):
		if self._virtuals == None:
			self._grab_virtuals()
		return self._virtuals[pkg.package][pkg.fullver]

	def _get_categories(self, *optionalCategory):
		# return if optionalCategory is passed... cause it's not yet supported
		if optionalCategory:
			return ()
		return ("virtual",)

	def _get_packages(self, category):
		if self._virtuals == None:
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
