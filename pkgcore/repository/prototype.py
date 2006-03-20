# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from weakref import proxy
from itertools import imap
from pkgcore.util.mappings import LazyValDict
from pkgcore.package.atom import atom

def ix_callable(*args):
	return "/".join(str(x) for x in args)

def mangle_empties(val):
	if len(val) == 0:
		return [""]
	return val

class IterValLazyValDict(LazyValDict):

	def __init__(self, key_func, val_func, override_iter=None):
		LazyValDict.__init__(self, key_func, val_func)
		self._iter_callable = override_iter
		
	def __iter__(self):
		if self._iter_callable is not None:
			return (ix_callable(k,x).strip("/") for k in self.iterkeys() for x in self._iter_callable(self[k]))
		else:
			return (ix_callable(k,x) for k in self.iterkeys() for x in self[k])

	def __contains__(self, key):
		return key in iter(self)

class tree(object):
	"""
	del raw_repo, and set it to the underlying repo if you're wrapping another repo"""
	raw_repo = None
	package_class = None
	configured = True
	configure = ()
	
	def __init__(self, frozen=True):
		self.categories = IterValLazyValDict(self._get_categories, self._get_categories, override_iter=mangle_empties)
		self.packages   = IterValLazyValDict(self.categories.__iter__, self._get_packages)
		self.versions   = IterValLazyValDict(self.packages.__iter__, self._get_versions)

		self.frozen = frozen
		self.lock = None

	def _get_categories(self, *args):
		"""this must return a list, or sequence"""
		raise NotImplementedError

	def _get_packages(self, category):
		"""this must return a list, or sequence"""
		raise NotImplementedError

	def _get_versions(self, package):
		"""this must return a list, or sequence"""
		raise NotImplementedError

	def __getitem__(self, cpv):
		cpv_inst = self.package_class(cpv)
		if cpv_inst.fullver not in self.versions[cpv_inst.key]:
			del cpv_inst
			raise KeyError(cpv)
		return cpv_inst

	def __setitem__(self, *values):
		raise AttributeError

	def __delitem__(self, cpv):
		raise AttributeError

	def __iter__(self):
		for cpv in self.versions:
			yield self.package_class(cpv)
		return

	def __len__(self):
		return len(self.versions)

	def match(self, atom):
		return list(self.itermatch(atom))

	def itermatch(self, restrict):
		if isinstance(restrict, atom):
			if restrict.category == None:
				candidates = self.packages
			else:
				if restrict.package == None:
					try:	candidates = self.packages[restrict.category]
					except KeyError:
						# just stop now.  no category matches == no yielded cpvs.
						return
				else:
					try:
						if restrict.package not in self.packages[restrict.category]:
							# no matches possible
							return
						candidates = [restrict.key]
					except KeyError:
						# restrict.category wasn't valid.  no matches possible.
						return
		else:
			candidates = self.packages

		#actual matching.
		for catpkg in candidates:
			for ver in self.versions[catpkg]:
				pkg = self.package_class(catpkg+"-"+ver)
				if restrict.match(pkg):
					yield pkg
		return

	def install(self, pkg, *a, **kw):
		if self.frozen:
			raise AttributeError("repo is frozen")
		return self._install(pkg, *a, **kw)

	def _install(self, pkg, *a, **kw):
		raise NotImplementedError

	def uninstall(self, pkg, *a, **kw):
		if self.frozen:
			raise AttributeError("repo is frozen")
		return self._uninstall(pkg, *a, **kw)

	def _uninstall(self,pkg, *a, **kw):
		raise NotImplementedError

	def replace(self, orig, new, *a, **kw):
		if self.frozen:
			raise AttributeError("repo is frozen")
		return self._replace(orig, new, *a, **kw)

	def _replace(self, orig, new, *a, **kw):
		raise NotImplementedError
