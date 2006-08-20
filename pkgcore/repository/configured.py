# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
wrap a repository, binding configuration to pkgs returned from the repository
"""

from pkgcore.util.compatibility import any
from pkgcore.restrictions.packages import PackageRestriction, OrRestriction, AndRestriction
from pkgcore.restrictions import boolean
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

	def itermatch(self, restrict, **kwds):
		if not any(True for r in collect_package_restrictions(restrict, self.attr_filters)):
			return (self.package_class(pkg) for pkg in self.raw_repo.itermatch(restrict, **kwds))
			
		def transform_solutions_array(array):
			if not array:
				return None
			elif len(array) == 1:
				if not array[0]:
					return None
				elif len(array[0]) == 1:
					restrict = array[0][0]
				else:
					restrict = AndRestriction(disable_inst_caching=True, *array[0])
			else:
				restrict = OrRestriction(disable_inst_caching=True,
					*[AndRestriction(disable_inst_caching=True, *filter(None, x)) for x in array if x])
			return restrict
		
		if hasattr(restrict, "cnf_solutions"):
			restrict_solutions = []
			for and_block in restrict.cnf_solutions():
				l = []
				for node in and_block:
					if isinstance(node, PackageRestriction):
						if node.attr in self.attr_filters:
							continue
					elif isinstance(node, boolean.base):
						node = [
							[a for a in filter(None, x) if a and not (isinstance(a, PackageRestriction) and
								a.attr in self.attr_filters)]
							for x in node.dnf_solutions(full_solution_expansion=True)]
						
						node = transform_solutions_array(node)
						if node is None:
							continue
					l.append(node)
				if l:
					restrict_solutions.append(l)
			filtered_restrict = transform_solutions_array(restrict_solutions)
			del restrict_solutions
		else:
			filtered_restrict = restrict
		
		# disable inst_caching for these restrictions.  it's a one time generation, and potentially
		# quite costly for hashing

		return (pkg for pkg in (self.package_class(x) for x in self.raw_repo.itermatch(filtered_restrict, 
			**kwds)) if restrict.force_True(pkg))

	itermatch.__doc__ = prototype.tree.itermatch.__doc__.replace("@param", "@keyword").replace("@keyword restrict:", "@param restrict:")

	def __getitem__(self, key):
		return self.package_class(self.raw_repo[key])

	def __iter__(self):
		return (self.package_class(cpv) for cpv in self.raw_repo)
