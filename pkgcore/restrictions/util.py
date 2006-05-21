# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.lists import iter_flatten
from pkgcore.util.containers import InvertedContains
from pkgcore.restrictions import packages

def collect_package_restrictions(restrict, attrs=None):
	"""walks a restriction, descending as neccessary and returning any PackageRestrictions that work
	on attrs passed in

	no attrs, yields all PackageRestriction instances"""
	if attrs is None:
		attrs = InvertedContains()
	elif isinstance(attrs, (list, tuple)):
		attrs = frozenset(attrs)
	return (r for r in iter_flatten(restrict) 
		if isinstance(r, packages.PackageRestriction) and r.attr in attrs)
