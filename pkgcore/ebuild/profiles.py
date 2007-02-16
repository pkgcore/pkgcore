# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import errno, os
from itertools import chain
from pkgcore.config import ConfigHint
from pkgcore.ebuild import const
from pkgcore.util.osutils import abspath, join as pjoin, readlines
from pkgcore.ebuild import ebuild_src
from pkgcore.util.containers import InvertedContains
from pkgcore.util.file import iter_read_bash, read_bash_dict
from pkgcore.util.caching import WeakInstMeta
from pkgcore.repository import virtual
from pkgcore.util.currying import partial
from pkgcore.util.demandload import demandload

demandload(globals(), "pkgcore.interfaces.data_source:local_source "
    "pkgcore.ebuild:cpv "
    "pkgcore.ebuild:atom "
    "pkgcore.repository:util "
    "pkgcore.restrictions:packages ")

class ProfileError(Exception):

    def __init__(self, path, filename, error):
        self.path, self.filename, self.error = path, filename, error

    def __str__(self):
        return "ProfileError: profile %r, file %r, error %s" % (
            self.path, self.filename, self.error)

def load_decorator(filename, handler=iter_read_bash, fallback=()):
    def f(func):
        def f2(self, *args):
            path = pjoin(self.path, filename)
            try:
                data = readlines(path, False, True, True)
                if data is None:
                    return func(self, fallback, *args)
                return func(self, handler(data), *args)
            except (KeyboardInterrupt, RuntimeError, SystemExit):
                raise
            except Exception, e:
                raise ProfileError(self.path, filename, e)
        return f2
    return f

def split_negations(data, func):
    neg, pos = [], []
    for line in data:
        if line[0] == '-':
            if len(line) == 1:
                raise ValueError("'-' negation without a token")
            neg.append(func(line[1:]))
        else:
            pos.append(func(line))
    return (tuple(neg), tuple(pos))


class ProfileNode(object):

    __metaclass__ = WeakInstMeta
    __inst_caching__ = True

    def __init__(self, path):
        if not os.path.isdir(path):
            raise ProfileError(path, "", "profile doesn't exist")
        self.path = path

    def __str__(self):
        return "Profile at %r" % self.path

    def __repr__(self):
        return '<%s path=%r, @%#8x>' % (self.__class__.__name__, self.path,
            id(self))

    @load_decorator("packages")
    def _load_packages(self, data):
        # sys packages and visibility
        sys, neg_sys, vis, neg_vis = [], [], [], []
        for line in data:
            if line[0] == '-':
                if line[1] == '*':
                    neg_sys.append(atom.atom(line[2:]))
                else:
                    neg_vis.append(atom.atom(line[1:], negate_vers=True))
            else:
                if line[0] == '*':
                    sys.append(atom.atom(line[1:]))
                else:
                    vis.append(atom.atom(line, negate_vers=True))

        self.system = (tuple(neg_sys), tuple(sys))
        self.visibility = (tuple(neg_vis), tuple(vis))

    @load_decorator("parent")
    def _load_parents(self, data):
        self.parents = tuple(ProfileNode(abspath(pjoin(self.path, x)))
            for x in data)
        return self.parents

    @load_decorator("package.provided")
    def _load_pkg_provided(self, data):
        self.pkg_provided = split_negations(data, cpv.CPV)
        return self.pkg_provided

    @load_decorator("virtuals")
    def _load_virtuals(self, data):
        d = {}
        for line in data:
            l = line.split()
            if len(l) != 2:
                raise ValueError("%r is malformated" % line)
            d[cpv.CPV(l[0]).package] = atom.atom(l[1])
        self.virtuals = d
        return d

    @load_decorator("package.mask")
    def _load_masks(self, data):
        self.masks = split_negations(data, atom.atom)
        return self.masks

    @load_decorator("deprecated", lambda i:i, None)
    def _load_deprecated(self, data):
        if data is not None:
            data = iter(data)
            try:
                replacement = data.next().strip()
                msg = "\n".join(x.lstrip("#").strip()
                    for x in data)
                data = (replacement, msg)
            except StopIteration:
                # only an empty replacement could trigger this; thus
                # formatted badly.
                raise ValueError("didn't specify a replacement profile")
        self.deprecated = data
        return data

    @load_decorator("use.mask")
    def _load_masked_use(self, data):
        d = self._load_pkg_use_mask()
        neg, pos = split_negations(data, str)
        if neg or pos:
            d[packages.AlwaysTrue] = (neg, pos)
        self.masked_use = d
        return d

    @load_decorator("package.use.mask")
    def _load_pkg_use_mask(self, data):
        d = {}
        for line in data:
            i = iter(line.split())
            a = atom.atom(i.next())
            neg, pos = d.setdefault(a, ([], []))
            for x in i:
                if x[0] == '-':
                    neg.append(x[1:])
                else:
                    pos.append(x)
        for k, v in d.iteritems():
            d[k] = tuple(tuple(x) for x in v)
        return d

    @load_decorator("use.force")
    def _load_forced_use(self, data):
        d = self._load_pkg_use_force()
        neg, pos = split_negations(data, str)
        if neg or pos:
            d[packages.AlwaysTrue] = (neg, pos)
        self.forced_use = d
        return d

    @load_decorator("package.use.force")
    def _load_pkg_use_force(self, data):
        d = {}
        for line in data:
            i = iter(line.split())
            a = atom.atom(i.next())
            neg, pos = d.setdefault(a, ([], []))
            for x in i:
                if x[0] == '-':
                    neg.append(x[1:])
                else:
                    pos.append(x)
        for k, v in d.iteritems():
            d[k] = tuple(tuple(x) for x in v)
        return d

    def _load_default_env(self):
        path = pjoin(self.path, "make.defaults")
        try:
            f = open(pjoin(self.path, "make.defaults"), "r")
        except IOError, ie:
            if ie.errno != errno.ENOENT:
                raise ProfileError(self.path, "make.defaults", ie)
            self.default_env = {}
            return self.default_env
        try:
            try:
                d = read_bash_dict(f)
            finally:
                f.close()
        except (KeyboardInterrupt, RuntimeError, SystemExit):
            raise
        except Exception ,e:
            raise ProfileError(self.path, "make.defaults", e)
        self.default_env = d
        return d

    def _load_bashrc(self):
        path = pjoin(self.path, "profile.bashrc")
        if os.path.exists(path):
            self.bashrc = local_source(path)
        else:
            self.bashrc = None
        return self.bashrc

    def __getattr__(self, attr):
        if attr in ("system", "visibility"):
            self._load_packages()
            return getattr(self, attr)
        # use objects getattr to bypass our own; prevents infinite recursion
        # if they request something non existant
        try:
            func = object.__getattribute__(self, "_load_%s" % attr)
        except AttributeError:
            raise AttributeError(self, attr)
        if func is None:
            raise AttributeError(attr)
        return func()


class EmptyRootNode(ProfileNode):

    parents = ()
    deprecated = None
    forced_use = masked_use = {}
    pkg_provided = visibility = system = ((), ())
    virtuals = {}


def incremental_expansion(orig, iterable, msg_prefix=''):
    for i in iterable:
        if i[0] == '-':
            i = i[1:]
            if not i:
                raise ValueError("%sencountered an incomplete negation, '-'"
                    % msg_prefix)
            orig.discard(i)
        else:
            orig.add(i)


class OnDiskProfile(object):

    pkgcore_config_type = ConfigHint({'basepath':'str', 'profile':'str',
        'incrementals':'list'}, required=('basepath', 'profile'),
        typename='profile')

    def __init__(self, basepath, profile, incrementals=const.incrementals,
        load_profile_base=True):
        self.basepath = basepath
        self.profile = profile
        self.node = ProfileNode(pjoin(basepath, profile))
        self.incrementals = incrementals
        self.load_profile_base = load_profile_base

    @property
    def arch(self):
        return self.default_env.get("ARCH")

    @property
    def deprecated(self):
        return self.node.deprecated

    def _load_stack(self):
        def f(node):
            for x in node.parents:
                for y in f(x):
                    yield y
            yield node

        l = list(f(self.node))
        if self.load_profile_base:
            l = [EmptyRootNode(self.basepath)] + l
        return tuple(l)

    def _collapse_use_dict(self, attr):
        d = {}
        for node in self.stack:
            d2 = getattr(node, attr)
            for key, value in d2.iteritems():
                s = d.get(key, None)
                if s is None:
                    if value[1]:
                        d[key] = set(value[1])
                    continue
                s.difference_update(value[0])
                s.update(value[1])
                if not s:
                    del d[key]
        return d

    def _collapse_generic(self, attr):
        s = set()
        for node in self.stack:
            val = getattr(node, attr)
            s.difference_update(val[0])
            s.update(val[1])
        return s

    def _collapse_env(self):
        d = {}
        inc = self.incrementals
        if not self.stack:
            return {}
        for profile in self.stack:
            for key, val in profile.default_env.iteritems():
                if key in inc:
                    val = val.split()
                    s = d.get(key, None)
                    if s is None:
                        s = d[key] = set()
                    incremental_expansion(s, val, "expanding %s make.defaults: " % profile)
                    if not s:
                        del d[key]
                else:
                    d[key] = val
        return d

    @property
    def use_expand(self):
        if "USE_EXPAND" in self.incrementals:
            return tuple(self.default_env["USE_EXPAND"])
        return tuple(self.default_env["USE_EXPAND"].split())

    def _collapse_virtuals(self):
        d = {}
        for profile in self.stack:
            d.update(profile.virtuals)
        self.virtuals = d
        self.make_virtuals_repo = partial(AliasedVirtuals, d)

    def _collapse_pkg_provided(self):
        d = {}
        for pkg in self._collapse_generic("pkg_provided"):
            d.setdefault(pkg.category, {}).setdefault(pkg.package,
                []).append(pkg.fullver)
        return util.SimpleTree(d, pkg_klass=PkgProvided)

    def _collapse_masks(self):
        return frozenset(chain(self._collapse_generic("masks"),
            self._collapse_generic("visibility")))

    def __getattr__(self, attr):
        if attr == "stack":
            self.stack = obj = self._load_stack()
        elif attr in ("forced_use", "masked_use"):
            obj = self._collapse_use_dict(attr)
            setattr(self, attr, obj)
        elif attr == "bashrc":
            obj = self.bashrc = tuple(x.bashrc
                for x in self.stack if x.bashrc is not None)
        elif attr == 'system':
            obj = self.system = self._collapse_generic(attr)
        elif attr == 'masks':
            obj = self.masks = self._collapse_masks()
        elif attr == 'default_env':
            obj = self.default_env = self._collapse_env()
        elif attr == 'virtuals':
            self._collapse_virtuals()
            obj = self.virtuals
        elif attr == 'make_virtuals_repo':
            self._collapse_virtuals()
            obj = self.make_virtuals_repo
        elif attr == 'provides_repo':
            obj = self.provides_repo = self._collapse_pkg_provided()
        elif attr == 'path':
            obj = self.node.path
        else:
            raise AttributeError(attr)
        return obj


class PkgProvided(ebuild_src.base):

    package_is_real = False
    __inst_caching__ = True

    keywords = InvertedContains(())

    def __init__(self, *a, **kwds):
        # 'None' repo.
        ebuild_src.base.__init__(self, None, *a, **kwds)
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
        return atom.atom("=%s-%s" % (self._virtuals[pkg.package].key, pkg.fullver))
