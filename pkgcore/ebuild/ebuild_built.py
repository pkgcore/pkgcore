# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
built ebuild packages (vdb packages and binpkgs are derivatives of this)
"""

from pkgcore.ebuild import ebuild_src
from pkgcore.util.mappings import IndeterminantDict
from pkgcore.package import metadata
from pkgcore.interfaces.data_source import local_source
from pkgcore.fs import scan
from pkgcore.util.currying import post_curry
from pkgcore.ebuild.conditionals import DepSet
from pkgcore.package.atom import atom
import ebd

def passthrough(inst, attr, rename=None):
	if rename is None:
		rename = attr
	return inst.data[rename]

def flatten_depset(inst, conditionals):
	return inst.evaluate_depset(conditionals)

class package(ebuild_src.package):

	"""
	built form of an ebuild
	"""
	
	immutable = True
	tracked_attributes = ebuild_src.package.tracked_attributes[:]
	tracked_attributes.extend(["contents", "use", "environment"])
	allow_regen = False

	_get_attr = dict(ebuild_src.package._get_attr)

	for x in ("_mtime_", "fetchables"):
		del _get_attr[x]
	del x

	_get_attr.update((x, post_curry(passthrough, x)) for x in ("contents", "environment", "raw_ebuild"))
	_get_attr.update((k, post_curry(lambda s, wrap, inst: wrap(inst(s), s.use), 
		ebuild_src.package._config_wrappables[k], ebuild_src.package._get_attr[k]))
		for k in filter(ebuild_src.package.tracked_attributes.__contains__,
		ebuild_src.package._config_wrappables))

	_get_attr["use"] = lambda s:s.data["USE"].split()
	_get_attr["depends"] = lambda s:DepSet("", atom)

	def _update_metadata(self, pkg):
		raise NotImplementedError()

	def _repo_install_op(self, features=None):
		return ebd.install_op(self, env_data_source=self.environment, features=features)

	def _repo_uninstall_op(self, features=None):
		return ebd.uninstall_op(self, env_data_source=self.environment, features=features)

	def _repo_replace_op(self, features=None):
		return ebd.replace_op(self, env_data_source=self.environment, features=features)

	def _fetch_metadata(self):
		return self._parent._get_metadata(self)


class package_factory(metadata.factory):
	child_class = package

	def _get_metadata(self, pkg):
		return self._parent_repo._get_metadata(pkg)

	def _get_new_child_data(self, cpv):
		return ([self._parent_repo._get_ebuild_path], {})


class fake_package_factory(package_factory):
	"""
	a fake package_factory, so that we can reuse the normal get_metadata hooks; a factory is generated per
	package instance, rather then one factory, N packages.

	Do not use this unless you know it's what your after; this is strictly for transitioning a built ebuild
	(still in the builddir) over to an actual repo.  It literally is a mapping of original package data
	to the new generated instances data store.
	"""

	def __init__(self, child_class):
		self.child_class = child_class
		self._parent_repo = None
	
	def __del__(self):
		pass

	_forced_copy = ebuild_src.package.tracked_attributes

	def new_package(self, pkg, image_root, environment_path):
		self.pkg = pkg
		self.image_root = image_root
		self.environment_path = environment_path
		# lambda redirects path to environment path
		obj = self.child_class(pkg.cpvstr, self, lambda *x:self.environment_path)
		for x in self._forced_copy:
			# bypass setattr restrictions.
			obj.__dict__[x] = getattr(self.pkg, x)
		obj.__dict__["use"] = self.pkg.use
		return obj

	def _get_metadata(self, pkg):
		return IndeterminantDict(self.__pull_metadata)

	def __pull_metadata(self, key):
		if key == "contents":
			return scan(self.image_root, offset=self.image_root)
		elif key == "environment":
			return local_source(self.environment_path)
		else:
			try:
				return getattr(self.pkg, key)
			except AttributeError:
				raise KeyError

def generate_new_factory(*a, **kw):
	return package_factory(*a, **kw).new_package
