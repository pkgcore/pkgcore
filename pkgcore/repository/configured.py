# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
wrap a repository, binding configuration to pkgs returned from the repository
"""

from pkgcore.util.compatibility import any
from pkgcore.restrictions.packages import PackageRestriction, OrRestriction, AndRestriction
from pkgcore.restrictions.util import collect_package_restrictions
from pkgcore.repository import prototype
from pkgcore.package.conditionals import PackageWrapper
from itertools import imap

class tree(prototype.tree):
	configured = True

	def __init__(self, raw_repo, wrapped_attrs):

		"""
		@param raw_repo: repo to wrap
		@type raw_repo: L{pkgcore.repository.prototype.tree}
		@param wrapped_attrs: sequence of attrs to wrap for each pkg
		"""

		# yes, we're intentionally not using tree's init.
		# not perfect I know.
		self.raw_repo = raw_repo
		self.wrapped_attrs = wrapped_attrs
		self.attr_filters = frozenset(wrapped_attrs.keys() + [self.configurable])

	def _get_pkg_kwds(self, pkg):
		raise NotImplementedError()

	def package_class(self, pkg, *a):
		kwds = self._get_pkg_kwds(pkg)
		kwds.setdefault("attributes_to_wrap", self.wrapped_attrs)
		return PackageWrapper(pkg, self.configurable, **kwds)

	def __getattr__(self, attr):
		return getattr(self.raw_repo, attr)

	def itermatch(self, restrict, restrict_solutions=None, **kwds):
		if not any(True for r in collect_package_restrictions(restrict, self.attr_filters)):
			return (self.package_class(pkg) for pkg in self.raw_repo.itermatch(restrict, restrict_solutions=restrict_solutions, **kwds))
			
		if restrict_solutions is None:
			if hasattr(restrict, "solutions"):
				restrict_solutions = restrict.solutions(full_solution_expansion=True)
			else:
				restrict_solutions = (restrict,)
			
		filtered_solutions = [
			[a for a in x if not (isinstance(a, PackageRestriction) and a.attr in self.attr_filters)]
			for x in restrict_solutions]

		# disable inst_caching for this restriction.  it's a one time generation, and potentially
		# quite costly for hashing
		filtered_restrict = OrRestriction(disable_inst_caching=True,
			*[AndRestriction(disable_inst_caching=True, *x) for x in filtered_solutions])

		return (self.package_class(pkg) for pkg in self.raw_repo.itermatch(filtered_restrict, 
			restrict_solutions=filtered_solutions, **kwds) if restrict.force_True(pkg))

	itermatch.__doc__ = prototype.tree.itermatch.__doc__.replace("@param", "@keyword").replace("@keyword restrict:", "@param restrict:")

	def __getitem__(self, key):
		return self.package_class(self.raw_repo[key])

	def __iter__(self):
		return (self.package_class(cpv) for cpv in self.raw_repo)
