# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
gentoo profile support
"""

import os
from pkgcore.config import profiles
from pkgcore.util.file import iter_read_bash, read_bash_dict
from pkgcore.util.currying import pre_curry
from pkgcore.ebuild.atom import atom
from pkgcore.config.basics import list_parser
from pkgcore.util.mappings import ProtectedDict
from pkgcore.interfaces.data_source import local_source
from pkgcore.repository import virtual
from pkgcore.ebuild import cpv
from pkgcore.util.demandload import demandload
demandload(globals(), "logging")

# Harring sez-
# This should be implemented as an auto-exec config addition.


def loop_iter_read(files, func=iter_read_bash):
    for fp in files:
        if os.path.exists(fp):
            try:
                yield fp, func(fp)
            except (OSError, IOError), e:
                raise profiles.ProfileException(
                    "failed reading '%s': %s" % (e.filename, str(e)))


def incremental_set(fp, iterable, stack):
    for p in iterable:
        if p[0] == "-":
            try:
                stack.remove(p[1:])
            except KeyError:
                logging.warn("%s is reversed in %s, but isn't set yet!"
                    % (p[1:], fp))
        else:
            stack.add(p)

def incremental_profile_files(stack, filename):
    s = set()
    pjoin = os.path.join
    for fp, i in loop_iter_read(pjoin(prof, filename) for prof in stack):
        incremental_set(fp, i, s)
    return s


class OnDiskProfile(profiles.base):

    """
    On disk profile to scan

    api subject to change (not stable)
    """

    def __init__(self, profile, incrementals=None, base_repo=None,
                 base_path=None):

        """
        @param profile: profile name to scan
        @param incrementals: sequence of settings to implement incremental
            stacking for.
        @param base_repo: L{pkgcore.ebuild.repository.UnconfiguredTree} to
            build this profile from, mutually exclusive with base_path.
        @param base_path: raw filepath for this profile.  Mutually exclusive
            to base_repo.
        """

        pjoin = os.path.join

        from pkgcore.config.errors import InstantiationError
        if incrementals is None:
            from pkgcore.ebuild import const
            incrementals = list(const.incrementals)
        if base_path is None and base_repo is None:
            raise InstantiationError(
                self.__class__, [profile], {"incrementals": incrementals,
                                            "base_repo": base_repo,
                                            "base_path": base_path},
                "either base_path, or location must be set")
        if base_repo is not None:
            self.basepath = pjoin(base_repo.base, "profiles")
        elif base_path is not None:
            if not os.path.exists(base_path):
                raise InstantiationError(
                    self.__class__, [profile], {
                        "incrementals": incrementals,
                        "base_repo": base_repo, "base_path": base_path},
                    "if defined, base_path(%s) must exist-" % base_path)
            self.basepath = base_path
        else:
            raise InstantiationError(
                self.__class__, [profile], {"incrementals": incrementals,
                                            "base_repo": base_repo,
                                            "base_path": base_path},
                "either base_repo or base_path must be configured")


        dep_path = pjoin(self.basepath, profile, "deprecated")
        if os.path.isfile(dep_path):
            logging.warn(
                "profile '%s' is marked as deprecated, read '%s' please" % (
                    profile, dep_path))
        del dep_path

        parents = [None]
        stack = [pjoin(self.basepath, profile.strip())]
        idx = 0

        while len(stack) > idx:
            parent, trg = parents[idx], stack[idx]

            if not os.path.isdir(trg):
                if parent:
                    raise profiles.ProfileException(
                        "%s doesn't exist, or isn't a dir, referenced by %s" %
                        (trg, parent))
                raise profiles.ProfileException(
                    "%s doesn't exist, or isn't a dir" % trg)

            fp = pjoin(trg, "parent")
            if os.path.isfile(fp):
                l = []
                try:
                    f = open(fp, "r", 32384)
                except (IOError, OSError):
                    raise profiles.ProfileException(
                        "failed reading parent from %s" % path)
                for x in f:
                    x = x.strip()
                    if x.startswith("#") or x == "":
                        continue
                    l.append(x)
                f.close()
                l.reverse()
                for x in l:
                    stack.append(os.path.abspath(pjoin(trg, x)))
                    parents.append(trg)
                del l

            idx += 1

        del parents

        # build up visibility limiters.
        stack.reverse()
        pkgs = set()
        for fp, i in loop_iter_read(pjoin(prof, "packages") for prof in stack):
            incremental_set(fp, i, pkgs)

        visibility = []
        sys = []
        for p in pkgs:
            if p[0] == "*":
                # system set.
                sys.append(atom(p[1:]))
            else:
                # note the negation. this means cat/pkg matchs, but
                # ver must not, else it's masked.
                visibility.append(atom(p, negate_vers=True))

        self.sys = tuple(sys)
        self.visibility = tuple(visibility)
        del sys, visibility, pkgs
        
        self.bashrc = tuple(local_source(path)
            for path in (pjoin(x, 'profile.bashrc') for x in stack)
                if os.path.exists(path))
        self.use_mask = tuple(incremental_profile_files(stack, "use.mask"))
        self.maskers = tuple(set(self.visibility).union(atom(x) for x in 
            incremental_profile_files(stack, "package.mask")))

        d = {}
        for fp, dc in loop_iter_read((pjoin(prof, "make.defaults")
                                      for prof in stack),
            lambda x:read_bash_dict(x, vars_dict=ProtectedDict(d))):
            for k, v in dc.items():
                # potentially make incrementals a dict for ~O(1) here,
                # rather then O(N)
                if k in incrementals:
                    v = list_parser(dc[k])
                    if k in d:
                        d[k] += v
                    else:
                        d[k] = v
                else:
                    d[k] = v

        d.setdefault("USE_EXPAND", '')
        if isinstance(d["USE_EXPAND"], str):
            self.use_expand = tuple(d["USE_EXPAND"].split())
        else:
            self.use_expand = ()

        # and... default virtuals.
        virtuals = {}
        for fp, i in loop_iter_read(pjoin(prof, "virtuals")
            for prof in stack):
            for p in i:
                p = p.split()
                c = cpv.CPV(p[0])
                virtuals[c.package] = atom(p[1])

        self.virtuals = pre_curry(AliasedVirtuals, virtuals)
        # collapsed make.defaults.  now chunkify the bugger.
        self.conf = d

    def cleanse(self):
        del self.visibility
        del self.system
        del self.use_mask
        del self.maskers


class ForgetfulDict(dict):

    def __setitem__(self, key, attr):
        return

    def update(self, other):
        return


class AliasedVirtuals(virtual.tree):

    """
    repository generated from a profiles default virtuals
    """

    def __init__(self, virtuals, repo):
        """
        @param virtuals: dict of virtual -> providers
        @param repo: L{pkgcore.ebuild.repository.UnconfiguredTree} parent repo
        """

        virtual.tree.__init__(self, virtuals)
        self.aliased_repo = repo
        self.versions._vals = ForgetfulDict()

    def _get_versions(self, catpkg):
        cat, pkg = catpkg.rsplit("/", 1)
        if cat != "virtual":
            raise KeyError("no %s package in this repository" % catpkg)
        return tuple(x.fullver
                     for x in self.aliased_repo.itermatch(self._virtuals[pkg]))

    def _fetch_metadata(self, pkg):
        return atom("=%s-%s" % (self._virtuals[pkg.package].key, pkg.fullver))
