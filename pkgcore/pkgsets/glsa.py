# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import logging
from xml.dom import minidom
import os
from pkgcore.util.repo_utils import get_virtual_repos
from pkgcore.util.compatibility import any
from pkgcore.util.iterables import caching_iter
from pkgcore.package import atom, cpv
from pkgcore.restrictions import packages, restriction, boolean
from pkgcore.config.introspect import ConfigHint

class KeyedAndRestriction(boolean.AndRestriction):

	type = packages.package_type

	def __init__(self, *a, **kwds):
		key = kwds.pop("key", None)
		tag = kwds.pop("tag", None)
		boolean.AndRestriction.__init__(self, *a, **kwds)
		self.key = key
		self.tag = tag

	def __str__(self):
		if self.tag is None:
			return boolean.AndRestriction.__str__(self)
		return "%s %s" % (self.tag, boolean.AndRestriction.__str__(self))

	def solutions(self, *a, **kwds):
		if self.key == "dev-db/postgresql":
			import pdb;pdb.set_trace()
		return boolean.AndRestriction.solutions(self, *a, **kwds)


class GlsaDirSet(object):

	pkgcore_config_type = ConfigHint(types={"src":"section_ref"})
	op_translate = {"ge":">=", "gt":">", "lt":"<", "le":"<=", "eq":"="}

	def __init__(self, src):
		"""src must be either full path to glsa dir, or a repo object to pull it from"""
		if not isinstance(src, basestring):
			src = os.path.join(get_virtual_repos(src, False)[0].base, "metadata/glsa")
		self.path = src
	
	def __iter__(self):
		for glsa, catpkg, pkgatom, vuln in self.iter_vulnerabilities():
			yield KeyedAndRestriction(pkgatom, vuln, finalize=True, key=catpkg, tag="GLSA vulnerable:")

	def pkg_grouped_iter(self, sorter=None):
		if sorter is None:
			sorter = iter
		pkgs = {}
		pkgatoms = {}
		for glsa, pkg, pkgatom, vuln in self.iter_vulnerabilities():
			pkgatoms[pkg] = pkgatom
			pkgs.setdefault(pkg, []).append(vuln)

		for pkgname in sorter(pkgs):
			yield KeyedAndRestriction(pkgatoms[pkgname], key=pkgname, *pkgs[pkgname])


	def iter_vulnerabilities(self):
		pkgs = {}
		for fn in os.listdir(self.path):
			#"glsa-1234-12.xml
			if not (fn.startswith("glsa-") and fn.endswith(".xml")):
				continue
			try:
				[int(x) for x in fn[5:-4].split("-")]
			except ValueError:
				continue
			root = minidom.parse(os.path.join(self.path, fn))
			glsa_node = root.getElementsByTagName('glsa')
			if not glsa_node:
				continue
			for affected in root.getElementsByTagName('affected'):
				for pkg in affected.getElementsByTagName('package'):
					try:
						pkgname = str(pkg.getAttribute('name')).strip()
						pkg_vuln_restrict = self.generate_intersects_from_pkg_node(pkg, 
							tag="glsa(%s)" % fn[5:-4])
						if pkg_vuln_restrict is None:
							continue
						pkgatom = atom.atom(pkgname)
						# some glsa suck.  intentionally trigger any failures now.
						str(pkgatom)
						yield fn[5:-4], pkgname, pkgatom, pkg_vuln_restrict
					except (TypeError, ValueError), v:
						# thrown from cpv.
						logging.warn("invalid glsa- %s, package %s: error %s" % (fn, pkgname, v))
						del v


	def generate_intersects_from_pkg_node(self, pkg_node, tag=None):
		vuln = pkg_node.getElementsByTagName("vulnerable")
		if not vuln:
			return None
		elif len(vuln) > 1:
			vuln_list = [self.generate_restrict_from_range(x) for x in vuln]
			vuln = packages.OrRestriction(finalize=True, *vuln_list)
		else:
			vuln_list = [self.generate_restrict_from_range(vuln[0])]
			vuln = vuln_list[0]
		invuln = pkg_node.getElementsByTagName("unaffected")
		if not invuln:
			return vuln
		invuln_list = [self.generate_restrict_from_range(x, negate=True) for x in invuln]
		invuln = [x for x in invuln_list if x not in vuln_list]
		if not invuln:
			if tag is None:
				return vuln
			return KeyedAndRestriction(vuln, tag=tag, finalize=True)
		return KeyedAndRestriction(vuln, finalize=True, tag=tag, *invuln)
#		elif len(invuln) == 1:
#			return KeyedAndRestriction(vuln, invuln[0], finalize=True, tag=tag)
#		return KeyedAndRestriction(vuln, packages.AndRestriction(finalize=True, *invuln),
#			finalize=True, tag=tag)

	def generate_restrict_from_range(self, node, negate=False):
		op = node.getAttribute("range").strip()
		base = cpv.CPV("bar/foo-%s" % str(node.childNodes[0].nodeValue.strip()))
		restrict = self.op_translate[op.lstrip("r")]
		if op.startswith("r"):
			return packages.AndRestriction(
				atom.VersionMatch("~", base.version),
				atom.VersionMatch(restrict, base.version, rev=base.revision),
				finalize=True, negate=True)
#			restrict = packages.AndRestriction(
#				atom.VersionMatch("~", base.version, negate=negate),
#				atom.VersionMatch(restrict, base.version, rev=base.revision, negate=negate),
#				finalize=True)
		return atom.VersionMatch(restrict, base.version, rev=base.revision, negate=negate)


def find_vulnerable_repo_pkgs(glsa_src, repo, grouped=False):
	if grouped:
		i = glsa_src.pkg_grouped_iter()
	else:
		i = iter(glsa_src)
	for restrict in i:
		matches = caching_iter(repo.itermatch(restrict, sorter=sorted))
		print "checking on ",restrict
		if matches:
			yield glsa_src, matches


class SecurityUpgrades(object):
	pkgcore_config_type = ConfigHint(types={"ebuild_repo":"section_ref", "vdb":"section_ref"})

	def __init__(self, ebuild_repo, vdb):
		self.glsa_src = GlsaDirSet(ebuild_repo)
		self.vdb = vdb

	def __iter__(self):
		for glsa, matches in find_vulnerable_repo_pkgs(self.glsa_src, self.vdb, grouped=True):
			import pdb;pdb.set_trace()
			yield KeyedAndRestriction(glsa[0], restriction.Negate(glsa[1]), finalize=True)

