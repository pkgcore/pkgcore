# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
implementation of the standard PORTDIR + PORTDIR_OVERLAY repository stacking
"""

from pkgcore.repository import multiplex
from pkgcore.config.introspect import ConfigHint
from pkgcore.config import errors
from pkgcore.ebuild import ebuild_repository, eclass_cache
from pkgcore.util.file import read_dict
from pkgcore.util.lists import unstable_unique
from pkgcore.restrictions import packages
import os, stat


class OverlayRepo(multiplex.tree):

	"""
	collapse multiple trees into one, with a shared eclass dir, and first package leftmost returned
	"""
	
	pkgcore_config_type = ConfigHint(types={"trees":"section_refs", "default_mirrors":"list", "cache": "section_ref"}, 
		required=("trees",), positional=("trees",))

	configured = False
	configurables = ("settings",)
	configure = ebuild_repository.ConfiguredTree

	def __init__(self, trees, **kwds):
		"""
		@param trees: L{pkgcore.ebuild.ebuild_repository.UnconfiguredTree} instances to combine
		@keywords cache: L{pkgcore.cache.template.databse} instance to use for caching for the combined tree
		"""

		if not trees or len(trees) < 2:
			raise errors.InstantiationError(self.__class__, trees, {}, 
				"Must specify at least two pathes to ebuild trees to overlay")

		cache = kwds.pop("cache", None)
		default_mirrors = kwds.pop("default_mirors", None)
		
#		for t in trees:
#			if not os.path.isdir(t):
#				raise errors.InstantiationError(self.__class__, trees, {}, 
#					"all trees must be ebuild_repository instances, and existant dirs- '%s' is not" % t)

		# master combined eclass
		self.eclass_cache = eclass_cache.StackedCache(*[t.eclass_cache for t in reversed(trees)])

		repos = []
		for t in trees:
			repos.append(t.rebind(cache=[cache]+t.cache, eclass_cache=self.eclass_cache, default_mirrors=default_mirrors))


#		try:
#			repos = [ebuild_repository.UnconfiguredTree(loc, cache=cache, eclass_cache=self.eclass_cache, 
#				**kwds) for loc in trees]
#		except (OSError, IOError), e:
#			raise errors.InstantiationError(self.__class__, trees, {},
#				"unable to initialize a sub tree- %s" % e)

		# now... we do a lil trick.  substitute the master mirrors in for each tree.
		master_mirrors = trees[0].mirrors
		for r in repos[1:]:
			for k, v in master_mirrors.iteritems():
				if k in r.mirrors:
					r.mirrors[k] = unstable_unique(r.mirrors[k] + v)
				else:
					r.mirrors[k] = v
		
		multiplex.tree.__init__(self, *repos)

	def _get_categories(self, *category):
		return tuple(unstable_unique(multiplex.tree._get_categories(self, *category)))

	def _get_packages(self, category):
		return tuple(unstable_unique(multiplex.tree._get_packages(self, category)))

	def _get_versions(self, catpkg):
		return tuple(unstable_unique(multiplex.tree._get_versions(self, catpkg)))

	def itermatch(self, *a, **kwds):
		s = set()
		for repo in self.trees:
			for pkg in repo.itermatch(*a, **kwds):
				if hash(pkg) not in s:
					yield pkg
					s.add(hash(pkg))

	def __iter__(self):
		return self.itermatch(packages.AlwaysTrue)
