# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from itertools import imap, ifilter
from pkgcore.util.mappings import LazyValDict
from pkgcore.util.lists import iter_stable_unique, iter_flatten
from pkgcore.package.atom import atom
from pkgcore.restrictions import packages, values, boolean
from pkgcore.util.compatibility import any
from pkgcore.restrictions.util import collect_package_restrictions

def ix_callable(a):
	return "/".join(a)

class IterValLazyDict(LazyValDict):

	def __init__(self, key_func, val_func, override_iter=None, return_func=ix_callable):
		LazyValDict.__init__(self, key_func, val_func)
		self._iter_callable = override_iter
		self.return_mangler = return_func

	def __iter__(self):
		return (self.return_mangler(k, ver) for k,v in self.iteritems() for ver in v)

	def __contains__(self, key):
		return key in iter(self)

	def __str__(self):
		return str(list(self))

	def force_regen(self, key):
		if key in self._vals:
			del self._vals[key]

class PackageIterValLazyDict(IterValLazyDict):

	def __iter__(self):
		return (k+"/"+x for k in self.iterkeys() for x in self[k])

	def __contains__(self, key):
		s = key.rsplit("/", 1)
		if len(s) != 2:
			return False
		return s[1] in self[s[0]]

class CategoryIterValLazyDict(IterValLazyDict):

	def force_add(self, key):
		try:
			# force lazyvaldict to do the _keys_func work
			self[key]
		except KeyError:
			self._keys.add(key)

	def force_remove(self, key):
		try:
			# force lazyvaldict to do the _keys_func work
			self[key]
			self._keys.remove(key)
			if key in self._vals:
				del self._vals[key]
		except KeyError:
			pass

	def __iter__(self):
		return self.iterkeys()

	def __contains__(self, key):
		return key in self.keys()


class tree(object):
	"""
	del raw_repo, and set it to the underlying repo if you're wrapping another repo"""
	raw_repo = None
	livefs = False
	package_class = None
	configured = True
	configure = ()

	def __init__(self, frozen=True):
		self.categories = CategoryIterValLazyDict(self._get_categories, self._get_categories)
		self.packages   = PackageIterValLazyDict(self.categories, self._get_packages)
		self.versions   = IterValLazyDict(self.packages, self._get_versions, return_func=lambda *t:"-".join(t))

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

	def match(self, atom, **kwds):
		return list(self.itermatch(atom, **kwds))

	def itermatch(self, restrict, restrict_solutions=None, sorter=None):
		"""yield matches one by one for restrict
		restriction_solutions is only useful if you've already split the restrict into it's seperate
		solutions.
		"""

		pkg_restrict = set()
		cat_restrict = set()
		cat_exact = set()
		pkg_exact = set()

		for x in collect_package_restrictions(restrict, ["category", "package"]):
			if x.attr == "category":
				cat_restrict.add(x.restriction)
			elif x.attr == "package":
				pkg_restrict.add(x.restriction)

		for e, s in ((pkg_exact, pkg_restrict), (cat_exact, cat_restrict)):
			l = [x.exact for x in e if isinstance(e, values.StrExactMatch) and not e.negate]
			s.difference_update(l)
			e.update(l)

		if cat_exact:
			cat_restrict.add(values.ContainmentMatch(cats_exact))
		del cat_exact
		if not cat_restrict:
			cats_iter = iter(self.categories)
		else:
			cats_iter = (x for x in self.categories if any(r.match(x) for r in cat_restrict))

		if pkg_exact:
			pkg_restrict.add(values.ContainmentMatch(pkg_exact))
		del pkg_exact
		if pkg_restrict:
			candidates = (self.packages.return_mangler((c,p)) for c in cats_iter for
				p in self.packages.get(c, []) if any(r.match(p) for r in pkg_restrict))
		else:
			if not cat_restrict:
				candidates = iter(self.packages)
			else:
				candidates = (self.packages.return_mangler((c,p)) 
					for c in cats_iter for p in self.packages.get(c, []))

		if sorter is None:
			sorter = iter
		for pkg in sorter(self._internal_match(candidates, restrict)):
			yield pkg

	def _internal_match(self, candidates, restrict):
		#actual matching.
		for catpkg in candidates:
			for ver in self.versions[catpkg]:
				pkg = self.package_class(catpkg+"-"+ver)
				if restrict.match(pkg):
					yield pkg

	def notify_remove_package(self, pkg):
		cp = "%s/%s" % (pkg.category, pkg.package)
		self.versions.force_regen(cp)
		if len(self.versions.get(cp, [])) == 0:
			# dead package
			self.packages.force_regen(pkg.category)
			if len(self.packages.get(pkg.category, [])) == 0:
				#  dead category
				self.categories.force_remove(pkg.category)
				self.packages.force_regen(pkg.category)
			self.versions.force_regen(cp)

	def notify_add_package(self, pkg):
		cp = "%s/%s" % (pkg.category, pkg.package)
		if pkg.category not in self.categories:
			self.categories.force_add(pkg.category)
		if cp not in self.packages:
			self.packages.force_regen(pkg.category)
		self.packages.force_regen(cp)

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

	def _uninstall(self, pkg, *a, **kw):
		raise NotImplementedError

	def replace(self, orig, new, *a, **kw):
		if self.frozen:
			raise AttributeError("repo is frozen")
		return self._replace(orig, new, *a, **kw)

	def _replace(self, orig, new, *a, **kw):
		raise NotImplementedError

	def __nonzero__(self):
		return any(x for x in self.versions)
