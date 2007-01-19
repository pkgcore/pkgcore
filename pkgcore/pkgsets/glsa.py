# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
Gentoo Linux Security Advisories (GLSA) support
"""

import os
from pkgcore.util.iterables import caching_iter
from pkgcore.restrictions import packages, restriction, boolean, values
from pkgcore.config import ConfigHint
from pkgcore.util.osutils import listdir_files, join as pjoin

from pkgcore.util.demandload import demandload
demandload(globals(), "pkgcore.util.xml:etree "
    "pkgcore.util.repo_utils:get_virtual_repos "
    "pkgcore.package:mutated "
    "pkgcore.ebuild:cpv,atom "
    "pkgcore.log:logger "
    )


class KeyedAndRestriction(boolean.AndRestriction):

    type = packages.package_type

    def __init__(self, *a, **kwds):
        key = kwds.pop("key", None)
        tag = kwds.pop("tag", None)
        boolean.AndRestriction.__init__(self, *a, **kwds)
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "tag", tag)

    def __str__(self):
        if self.tag is None:
            return boolean.AndRestriction.__str__(self)
        return "%s %s" % (self.tag, boolean.AndRestriction.__str__(self))


class GlsaDirSet(object):

    """
    generate a pkgset based on GLSA's distributed via a directory.

    (rsync tree is the usual source.)
    """

    pkgcore_config_type = ConfigHint({'src': 'ref:repo'}, typename='pkgset')
    op_translate = {"ge":">=", "gt":">", "lt":"<", "le":"<=", "eq":"="}

    def __init__(self, src):
        """
        @param src: where to get the glsa from
        @type src: must be either full path to glsa dir, or a repo object
            to pull it from
        """

        if not isinstance(src, basestring):
            src = filter(os.path.isdir, 
                (pjoin(repo.base, 'metadata', 'glsa') for repo in
                    get_virtual_repos(src, False) if hasattr(repo, 'base'))
                )
        else:
            src = [src]
        self.paths = src

    def __iter__(self):
        for glsa, catpkg, pkgatom, vuln in self.iter_vulnerabilities():
            yield KeyedAndRestriction(pkgatom, vuln, finalize=True, key=catpkg,
                                      tag="GLSA vulnerable:")

    def pkg_grouped_iter(self, sorter=None):
        """
        yield GLSA restrictions grouped by package key

        @param sorter: must be either None, or a comparison function
        """

        if sorter is None:
            sorter = iter
        pkgs = {}
        pkgatoms = {}
        for glsa, pkg, pkgatom, vuln in self.iter_vulnerabilities():
            pkgatoms[pkg] = pkgatom
            pkgs.setdefault(pkg, []).append(vuln)

        for pkgname in sorter(pkgs):
            yield KeyedAndRestriction(pkgatoms[pkgname],
                                      packages.OrRestriction(*pkgs[pkgname]),
                                      key=pkgname)


    def iter_vulnerabilities(self):
        """
        generator yielding each GLSA restriction
        """
        for path in self.paths:
            for fn in listdir_files(path):
                #"glsa-1234-12.xml
                if not (fn.startswith("glsa-") and fn.endswith(".xml")):
                    continue
                try:
                    [int(x) for x in fn[5:-4].split("-")]
                except ValueError:
                    continue
                root = etree.parse(pjoin(path, fn))
                glsa_node = root.getroot()
                if glsa_node.tag != 'glsa':
                    raise ValueError("glsa without glsa rootnode")
                for affected in root.findall('affected'):
                    for pkg in affected.findall('package'):
                        try:
                            pkgname = str(pkg.get('name')).strip()
                            pkg_vuln_restrict = \
                                self.generate_intersects_from_pkg_node(
                                pkg, tag="glsa(%s)" % fn[5:-4])
                            if pkg_vuln_restrict is None:
                                continue
                            pkgatom = atom.atom(pkgname)
                            yield fn[5:-4], pkgname, pkgatom, pkg_vuln_restrict
                        except (TypeError, ValueError), v:
                            # thrown from cpv.
                            logger.warn("invalid glsa- %s, package %s: error %s"
                                % (fn, pkgname, v))
                            del v


    def generate_intersects_from_pkg_node(self, pkg_node, tag=None):
        arch = pkg_node.get("arch")
        if arch is not None:
            arch = str(arch.strip()).split()
            if not arch or "*" in arch:
                arch = None

        vuln = list(pkg_node.findall("vulnerable"))
        if not vuln:
            return None
        elif len(vuln) > 1:
            vuln_list = [self.generate_restrict_from_range(x) for x in vuln]
            vuln = packages.OrRestriction(finalize=True, *vuln_list)
        else:
            vuln_list = [self.generate_restrict_from_range(vuln[0])]
            vuln = vuln_list[0]
        if arch is not None:
            vuln = packages.AndRestriction(vuln, packages.PackageRestriction(
                    "keywords", values.ContainmentMatch(all=False, *arch)))
        invuln = (pkg_node.findall("unaffected"))
        if not invuln:
            # wrap it.
            return KeyedAndRestriction(vuln, tag=tag, finalize=True)
        invuln_list = [self.generate_restrict_from_range(x, negate=True)
                       for x in invuln]
        invuln = [x for x in invuln_list if x not in vuln_list]
        if not invuln:
            if tag is None:
                return KeyedAndRestriction(vuln, tag=tag, finalize=True)
            return KeyedAndRestriction(vuln, tag=tag, finalize=True)
        return KeyedAndRestriction(vuln, finalize=True, tag=tag, *invuln)

    def generate_restrict_from_range(self, node, negate=False):
        op = str(node.get("range").strip())
        base = str(node.text.strip())
        glob = base.endswith("*")
        if glob:
            base = base[:-1]
        base = cpv.CPV("cat/pkg-%s" % base)
        restrict = self.op_translate[op.lstrip("r")]
        if op.startswith("r"):
            if glob:
                raise ValueError("glob cannot be used with %s ops" % op)
            elif not base.revision:
                if '=' not in restrict:
                    # this is a non-range.
                    raise ValueError(
                        "range %s version %s is a guranteed empty set" %
                        (op, str(node.text.strip())))
                return atom.VersionMatch("~", base.version, negate=negate)
            return packages.AndRestriction(
                atom.VersionMatch("~", base.version),
                atom.VersionMatch(restrict, base.version, rev=base.revision),
                finalize=True, negate=negate)
        if glob:
            return packages.PackageRestriction("fullver",
                values.StrGlobMatch(base.fullver))
        return atom.VersionMatch(restrict, base.version, rev=base.revision,
                                 negate=negate)


def find_vulnerable_repo_pkgs(glsa_src, repo, grouped=False, arch=None):
    """
    generator yielding GLSA restrictions, and vulnerable pkgs from a repo.

    @param glsa_src: GLSA pkgset to pull vulnerabilities from
    @param repo: repo to scan for vulnerable packages
    @param grouped: if grouped, combine glsa restrictions into one restriction
        (thus yielding a pkg only once)
    @param arch: arch to scan for, x86 for example
    """

    if grouped:
        i = glsa_src.pkg_grouped_iter()
    else:
        i = iter(glsa_src)
    if arch is None:
        wrapper = lambda p: p
    else:
        if isinstance(arch, basestring):
            arch = (arch,)
        else:
            arch = tuple(arch)
        wrapper = lambda p: mutated.MutatedPkg(p, {"keywords":arch})
    for restrict in i:
        matches = caching_iter(wrapper(x)
                               for x in repo.itermatch(restrict,
                                                       sorter=sorted))
        if matches:
            yield restrict, matches


class SecurityUpgrades(object):

    """
    pkgset that can be used directly from pkgcore configuration.

    generates set of restrictions of required upgrades.
    """

    pkgcore_config_type = ConfigHint({'ebuild_repo': 'ref:repo',
                                      'vdb': 'ref:vdb'},
                                     typename='pkgset')

    def __init__(self, ebuild_repo, vdb, arch):
        self.glsa_src = GlsaDirSet(ebuild_repo)
        self.vdb = vdb
        self.arch = arch

    def __iter__(self):
        for glsa, matches in find_vulnerable_repo_pkgs(self.glsa_src, self.vdb,
                                                       grouped=True,
                                                       arch=self.arch):
            yield KeyedAndRestriction(glsa[0], restriction.Negate(glsa[1]),
                                      finalize=True)

