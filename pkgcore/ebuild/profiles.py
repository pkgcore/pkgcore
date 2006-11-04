# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
gentoo profile support
"""

import os, errno
from pkgcore.config import profiles, ConfigHint
from pkgcore.util.file import iter_read_bash, read_bash_dict
from pkgcore.util.currying import partial
from pkgcore.ebuild.atom import atom
from pkgcore.config.basics import list_parser
from pkgcore.util.mappings import ProtectedDict
from pkgcore.interfaces.data_source import local_source
from pkgcore.repository import virtual, util
from pkgcore.ebuild import cpv, ebuild_src
from pkgcore.util.demandload import demandload
from pkgcore.util.osutils import join as pjoin
from collections import deque

demandload(globals(),
    "pkgcore.config.errors:InstantiationError "
    "pkgcore.ebuild:const "
    "pkgcore.log:logger "
    "pkgcore.util.containers:InvertedContains ")


# Harring sez-
# This should be implemented as an auto-exec config addition.

def loop_stack(stack, filename, func=iter_read_bash):
    return loop_iter_read((pjoin(x, filename) for x in stack),
        func=func)

def loop_iter_read(files, func=iter_read_bash):
    for fp in files:
        try:
            if func == iter_read_bash:
                yield fp, func(open(fp, "r"))
            else:
                yield fp, func(fp)
        except (OSError, IOError), e:
            if e.errno != errno.ENOENT:
                raise profiles.ProfileException(
                    "failed reading '%s': %s" % (e.filename, str(e)))
            del e

def incremental_profile_files(stack, filename):
    s = set()
    for fp, i in loop_iter_read(pjoin(prof, filename) for prof in stack):
        incremental_negations(fp, i, s)
    return s


def incremental_negations(setting, orig_list, orig_set=None):
    l = orig_set
    if l is None:
        l = set()
    for x in orig_list:
        if x[0] == "-":
            if x == "-*":
                l.clear()
            else:
                if len(x) == 1:
                    raise ValueError("negation of a setting in '%s', "
                         "but name negated isn't completed (%s)" % (
                         setting, orig_list))
                x = x[1:]
                if x in l:
                    l.remove(x)
        else:
            l.add(x)
    return l


class OnDiskProfile(profiles.base):

    """
    On disk profile to scan

    api subject to change (not stable)
    """
    _types = {'profile': 'str', 'base_path': 'str'}
    for thing in const.incrementals:
        _types[thing] = 'list'
    for thing in ['profile_incrementals', 'package.keywords', 'package.use',
                  'package.unmask', 'package.mask']:
        _types[thing] = 'list'

    pkgcore_config_type = ConfigHint(
        _types, typename='profile', incrementals=const.incrementals)
    del _types, thing

    def __init__(self, profile, incrementals=const.incrementals,
                 base_repo=None, base_path=None):

        """
        @param profile: profile name to scan
        @param incrementals: sequence of settings to implement incremental
            stacking for.
        @param base_repo: L{pkgcore.ebuild.repository.UnconfiguredTree} to
            build this profile from, mutually exclusive with base_path.
        @param base_path: raw filepath for this profile.  Mutually exclusive
            to base_repo.
        """

        profile = profile.strip()

        if base_path is None and base_repo is None:
            raise InstantiationError(
                "either base_path or location must be set")

        if base_repo is not None:
            self.basepath = pjoin(base_repo.base, "profiles")
        elif base_path is not None:
            if not os.path.exists(base_path):
                raise InstantiationError(
                    "if defined, base_path(%s) must exist-" % base_path)
            self.basepath = base_path

        else:
            raise InstantiationError(
                "either base_repo or base_path must be configured")

        self.load_deprecation_status(profile)

        stack = self.get_inheritance_order(profile)

        # build up visibility limiters.
        stack.reverse()

        pkgs = incremental_profile_files(stack, "packages")

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
        self.use_force = tuple(incremental_profile_files(stack, "use.force"))

        self.maskers = tuple(set(self.visibility).union(atom(x) for x in 
            incremental_profile_files(stack, "package.mask")))
        pkg_provided = {}
        for x in incremental_profile_files(stack, "package.provided"):
            a = cpv.CPV(x)
            pkg_provided.setdefault(a.category, {}).setdefault(
                a.package, []).append(a.fullver)

        if pkg_provided:
            i = InvertedContains(())
            ptree = util.SimpleTree(pkg_provided,
                pkg_klass=partial(PkgProvided, i))
        else:
            ptree = None
        self.package_provided_repo = ptree

        self.package_use_mask  = self.load_atom_dict(stack,
            "package.use.mask")
        self.package_use_force = self.load_atom_dict(stack,
            "package.use.force")

        d = {}
        for fp, dc in loop_iter_read((pjoin(prof, "make.defaults")
                                      for prof in stack),
            lambda x:read_bash_dict(x, vars_dict=ProtectedDict(d))):
            for k, v in dc.iteritems():
                # potentially make incrementals a dict for ~O(1) here,
                # rather then O(N)
                if k in incrementals and k in d:
                    # We have to keep the value in d a string or
                    # read_bash_dict explodes if it tries to expand it.
                    d[k] += ' ' + v
                else:
                    d[k] = v

        for k in incrementals:
            v = d.get(k)
            if v is not None:
                d[k] = list_parser(v)
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

        self.virtuals = partial(AliasedVirtuals, virtuals)
        # collapsed make.defaults.  now chunkify the bugger.
        self.conf = d

    def cleanse(self):
        del self.visibility
        del self.system
        del self.use_mask
        del self.maskers

    @property
    def arch(self):
        return self.conf.get("ARCH", None)

    @property
    def deprecated(self):
        if isinstance(self._deprecated, basestring):
            return open(self._deprecated, "r").read()
        return False

    def load_deprecation_status(self, profile):
        dep_path = pjoin(self.basepath, profile, "deprecated")
        self._deprecated = False
        if os.path.isfile(dep_path):
            logger.warn("profile '%s' is marked as deprecated, read '%s' "
                "please" % (profile, dep_path))
            self._deprecated = dep_path

    def load_atom_dict(self, stack, filename):
        d = {}
        for fp, i in loop_stack(stack, filename):
            for line in i:
                s = line.split()
                a = atom(s[0])
                d2 = d.setdefault(a.key, {})
                o = s[1:]
                if a in d2:
                    o = incremental_negations(fp, d2[a] + o)
                d2[a] = o
        return d

    def get_inheritance_order(self, profile):
        pabs = os.path.abspath
        # processed, required, loc, name
        full_stack = [pjoin(self.basepath, profile)]
        stack = deque([[False, full_stack[-1]]])
        idx = 0

        while stack:
            processed, trg = stack[-1]
            if processed:
                stack.pop()
                continue
            if len(stack) > 1:
                parent = stack[-2][1]
            else:
                parent = None
            
            new_parents = []

            try:
                for x in open(pjoin(trg, "parent")):
                    x = x.strip()
                    if x.startswith("#") or x == "":
                        continue
                    new_parents.append(x)

                new_parents = [pabs(pjoin(trg, x))
                    for x in reversed(new_parents)]
            except (IOError, OSError), oe:
                if oe.errno != errno.ENOENT:
                    if parent:
                        raise profiles.ProfileException(
                            "%s failed reading parent %s: %s" %
                            (parent, trg, oe))
                    raise profiles.ProfileException(
                        "%s failed reading: %s" % (trg, oe))

                if not os.path.exists(trg):
                    # never required without a parent.
                    if oe.errno == errno.ENOENT:
                        s = "doesn't exist"
                    else:
                        s = "wasn't found: %s" % oe
                    raise profiles.ProfileException(
                        "%s: parent %s %s" % 
                            (parent, trg, s))
                # ok.  no parent, non error.
                del oe
            if not new_parents:
                stack.pop()
            else:
                stack[-1][0] = True
                stack.extend([False, x] for x in new_parents)
                full_stack.extend(new_parents)
        return full_stack


class PkgProvided(ebuild_src.base):

    package_is_real = False

    def __init__(self, keywords, *a, **kwds):
        # 'None' repo.
        ebuild_src.base.__init__(self, None, *a, **kwds)
        object.__setattr__(self, "keywords", keywords)
        object.__setattr__(self, "use", [])
        object.__setattr__(self, "data", {})


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
        if catpkg[0] != "virtual":
            raise KeyError("no %s package in this repository" % catpkg)
        return tuple(x.fullver
            for x in self.aliased_repo.itermatch(self._virtuals[catpkg[1]]))

    def _fetch_metadata(self, pkg):
        return atom("=%s-%s" % (self._virtuals[pkg.package].key, pkg.fullver))
