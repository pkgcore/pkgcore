# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.repository import prototype
from pkgcore.package.conditionals import PackageWrapper

class tree(prototype.tree):
	configured = True
	
	def __init__(self, wrapped_attrs):
		# yes, we're intentionally not using tree's init.
		# not perfect I know.
		self.wrapped_attrs = wrapped_attrs

	def _get_pkg_kwds(self, pkg):
		raise NotImplementedError()
		
	def package_class(self, *a):
		pkg = self.raw_repo.package_class(*a)
		kwds = self._get_pkg_kwds(pkg)
		kwds.setdefault("attributes_to_wrap", self.wrapped_attrs)
		return PackageWrapper(pkg, self.configurable, **kwds)

	def __getattr__(self, attr):
		return getattr(self.raw_repo, attr)
		
