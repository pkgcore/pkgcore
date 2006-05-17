# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import logging
from xml.dom import minidom
import os
from pkgcore.util.repo_utils import get_virtual_repos
from pkgcore.util.compatibility import any
from pkgcore.package import atom, cpv
from pkgcore.restrictions import packages

class GlsaDirSet(object):

	op_translate = {"ge":">=", "gt":">", "lt":"<", "le":"<=", "eq":"="}

	def __init__(self, ebuild_repo, vdb):
		self.path = os.path.join(get_virtual_repos(ebuild_repo, False)[0].base, "metadata/glsa")
		self.vdb = vdb
	
	def __iter__(self):
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
				try:
					for pkg in affected.getElementsByTagName('package'):
						pkgname = str(pkg.getAttribute('name')).strip()
						pkg_vuln_restrict = self.generate_intersects_from_pkg_node(pkg)
						if pkg_vuln_restrict is None:
							continue
						pkgs.setdefault(pkgname, []).append(pkg_vuln_restrict)
				except ValueError, v:
					# thrown from cpv.
					logging.warn("invalid glsa- %s, package %s: error %s" % (fn, pkgname, v))
		if not pkgs:
			return
		for pkgname, restricts in pkgs.iteritems():
			pkgatom = atom.atom(pkgname)
			if any(True for x in self.vdb.itermatch(packages.AndRestriction(pkgatom, 
				packages.OrRestriction(*restricts)))):
				yield packages.AndRestriction(pkgatom, packages.OrRestriction(negate=True, finalize=True, *restricts))


	def generate_intersects_from_pkg_node(self, pkg_node):
		vuln = pkg_node.getElementsByTagName("vulnerable")
		if not vuln:
			return None
		elif len(vuln) > 1:
			vuln = packages.OrRestriction(finalize=True, 
				*[self.generate_restrict_from_range(x) for x in vuln])
		else:
			vuln = self.generate_restrict_from_range(vuln[0])
		invuln = pkg_node.getElementsByTagName("unaffected")
		if not invuln:
			return vuln
		elif len(invuln) > 1:
			invuln = packages.OrRestriction(finalize=True, negate=True, 
				*[self.generate_restrict_from_range(x) for x in invuln])
		else:
			invuln = self.generate_restrict_from_range(invuln[0], negate=True)

		return packages.AndRestriction(vuln, invuln, finalize=True)
			

	def generate_restrict_from_range(self, node, negate=False):
		op = node.getAttribute("range").strip()
		base = cpv.CPV("bar/foo-%s" % str(node.childNodes[0].nodeValue.strip()))
		restrict = self.op_translate[op.lstrip("r")]
		if op.startswith("r"):
			restrict = packages.AndRestriction(
				atom.VersionMatch("~", base.version),
				atom.VersionMatch(restrict, base.version, rev=base.revision),
				finalize=True, negate=negate)
		else:
			restrict = atom.VersionMatch(restrict, base.version, rev=base.revision, negate=negate)
		return restrict
