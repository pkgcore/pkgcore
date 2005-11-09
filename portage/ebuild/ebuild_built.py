# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id:$

from portage.ebuild import ebuild_src
from portage.util.mappings import ImmutableDict
from portage.package import metadata, base

class built(base.base):
	
	def __init__(self, pkg, contents, environment):
		import warnings
		warnings.warn("%s is going to go away soon, please contact harring if you're using this" % str(self.__class__))
		for x in ("fetchables", "depends", "rdepends", "description", "license", "use", "slot", "package", "version", "category"):
			setattr(self, x, getattr(pkg, x))
		self.contents = contents
		self.bundled_data = ImmutableDict({"environment":environment})

def passthrough(inst, attr):
	return inst.data[attr.upper()]

def forced_evaluate(inst, obj):
	return obj.evaluate_depset(inst.use)

class package(ebuild_src.package):
	immutable = True
	_subbed_attrs = {}
	_wrapped_attrs = {}
	for x in ["depends", "rdepends", "license", "slot"]:
		_wrapped_attrs[x] = forced_evaluate
	del x
	_subbed_attrs["fetchables"] = lambda *a: []
	_subbed_attrs["use"] = lambda *a: passthrough(*a).split()
	_subbed_attrs["contents"] = passthrough

	allow_regen = False

	def __getattr__(self, attr):
		if attr in self._subbed_attrs:
			obj = self._subbed_attrs[attr](self, attr)
			self.__dict__[attr] = obj
		else:
			obj = ebuild_src.package.__getattr__(self, attr)
		
		if attr in self._wrapped_attrs:
			obj = self._wrapped_attrs[attr](self, obj)
			self.__dict__[attr] = obj
		return obj


class package_factory(metadata.factory):
	child_class = package

	def _get_metadata(self, pkg):
		return self._parent_repo._get_metadata(pkg)

	def _get_new_child_data(self, cpv):
		return ([self._parent_repo._get_ebuild_path], {})

def generate_new_factory(*a, **kw):
	return package_factory(*a, **kw).new_package
