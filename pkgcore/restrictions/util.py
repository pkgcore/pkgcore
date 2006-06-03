# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.lists import iter_flatten
from pkgcore.util.containers import InvertedContains
from pkgcore.restrictions import packages, boolean

def _is_package_instance(inst):
	return getattr(inst, "type", None) == packages.package_type and not isinstance(inst, boolean.base)

def collect_package_restrictions(restrict, attrs=None):
	"""walks a restriction, descending as neccessary and returning any PackageRestrictions that work
	on attrs passed in

	no attrs, yields all PackageRestriction instances"""
	if attrs is None:
		attrs = InvertedContains()
	elif isinstance(attrs, (list, tuple)):
		attrs = frozenset(attrs)
	return (r for r in iter_flatten(restrict, _is_package_instance) 
		if r.attr in attrs)
