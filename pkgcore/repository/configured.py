# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.restrictions import boolean
from pkgcore.restrictions.packages import PackageRestriction, OrRestriction, AndRestriction
from pkgcore.repository import prototype
from pkgcore.package.conditionals import PackageWrapper
from pkgcore.util.compatibility import any
from pkgcore.util.lists import iter_flatten
from itertools import imap

class tree(prototype.tree):
	configured = True

	def __init__(self, wrapped_attrs):
		# yes, we're intentionally not using tree's init.
		# not perfect I know.
		self.wrapped_attrs = wrapped_attrs
		self.attr_filters = frozenset(wrapped_attrs.keys() + [self.configurable])

	def _get_pkg_kwds(self, pkg):
		raise NotImplementedError()

	def package_class(self, *a):
		pkg = self.raw_repo.package_class(*a)
		kwds = self._get_pkg_kwds(pkg)
		kwds.setdefault("attributes_to_wrap", self.wrapped_attrs)
		return PackageWrapper(pkg, self.configurable, **kwds)

	def __getattr__(self, attr):
		return getattr(self.raw_repo, attr)
	
	def itermatch(self, restrict, restrict_solutions=None, **kwds):
		if restrict_solutions is None:
			if hasattr(restrict, "solutions"):
				restrict_solutions = restrict.solutions(full_solution_expansion=True)
			else:
				restrict_solutions = (restrict,)

		filtered_solutions = [
			[a for a in x if not (isinstance(a, PackageRestriction) and a.attr in self.attr_filters)]
			for x in restrict_solutions]

		# second walk of the list.  ick.
		if sum(imap(len, restrict_solutions)) == sum(imap(len, filtered_solutions)):
			# well.  that was an expensive waste of time- doesn't check anything we care about.
			return prototype.tree.itermatch(self, restrict, restrict_solutions=restrict_solutions, **kwds)

		# disable inst_caching for this restriction.  it's a one time generation, and potentially
		# quite costly for hashing
		filtered_restrict = OrRestriction(disable_inst_caching=True,
			*[AndRestriction(disable_inst_caching=True, *x) for x in filtered_solutions])

		return (pkg for pkg in prototype.tree.itermatch(self, filtered_restrict, 
			restrict_solutions=filtered_solutions, **kwds) if restrict.force_True(pkg))
