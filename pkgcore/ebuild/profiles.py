# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

__all__ = ("ProfileError", "ProfileNode", "EmptyRootNode", "OnDiskProfile",
    "UserProfile", "PkgProvided", "AliasedVirtuals")

import errno, os
from itertools import chain
from snakeoil.iterables import chain_from_iterable

from pkgcore.config import ConfigHint
from pkgcore.ebuild import const, ebuild_src, misc
from pkgcore.ebuild.misc import (incremental_expansion, restrict_payload,
    _build_cp_atom_payload, chunked_data, ChunkedDataDict, split_negations,
    IncrementalsDict)
from pkgcore.repository import virtual

from snakeoil.osutils import abspath, join as pjoin, readlines_utf8
from snakeoil.containers import InvertedContains
from snakeoil.fileutils import iter_read_bash, read_bash_dict
from snakeoil import klass, caching, currying, sequences
from snakeoil import compatibility
from snakeoil.demandload import demandload

demandload(globals(),
    'snakeoil.data_source:local_source',
    'pkgcore.ebuild:cpv,atom',
    'pkgcore.ebuild.eapi:get_eapi',
    'pkgcore.repository:util',
    'pkgcore.restrictions:packages',
    'snakeoil:mappings',
)


class ProfileError(Exception):

    def __init__(self, path, filename, error):
        self.path, self.filename, self.error = path, filename, error

    def __str__(self):
        return "ProfileError: profile %r, file %r, error %s" % (
            self.path, self.filename, self.error)


def load_property(filename, handler=iter_read_bash, fallback=(),
    read_func=readlines_utf8):
    def f(func):
        f2 = klass.jit_attr_named('_%s' % (func.__name__,))
        return f2(currying.partial(_load_and_invoke, func, filename, handler, fallback,
            read_func))
    return f

def _load_and_invoke(func, filename, handler, fallback, read_func, self):
    path = pjoin(self.path, filename)
    try:
        data = read_func(path, True, True, True)
        if data is None:
            return func(self, fallback)
        if handler:
            data = handler(data)
        return func(self, data)
    except (KeyboardInterrupt, RuntimeError, SystemExit):
        raise
    except ProfileError:
        # no point in wrapping/throwing..
        raise
    except Exception, e:
        compatibility.raise_from(ProfileError(self.path, filename, e))


_make_incrementals_dict = currying.partial(IncrementalsDict, const.incrementals)

def _open_utf8(path, *args):
    try:
        if compatibility.is_py3k:
            return open(path, 'r', encoding='utf8')
        return open(path, 'r')
    except EnvironmentError, e:
        if errno.ENOENT != e.errno:
            raise
        return None


class ProfileNode(object):

    __metaclass__ = caching.WeakInstMeta
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

    system = klass.alias_attr("packages.system")
    visibility = klass.alias_attr("packages.visibility")

    _packages_kls = sequences.namedtuple("packages", ("system", "visibility"))

    @load_property("packages")
    def packages(self, data):
        # sys packages and visibility
        sys, neg_sys, vis, neg_vis = [], [], [], []
        for line in data:
            if line[0] == '-':
                if line[1] == '*':
                    neg_sys.append(self.eapi_atom(line[2:]))
                else:
                    neg_vis.append(self.eapi_atom(line[1:], negate_vers=True))
            else:
                if line[0] == '*':
                    sys.append(self.eapi_atom(line[1:]))
                else:
                    vis.append(self.eapi_atom(line, negate_vers=True))
        return self._packages_kls((tuple(neg_sys), tuple(sys)),
            (tuple(neg_vis), tuple(vis)))

    @load_property("parent")
    def parents(self, data):
        kls = getattr(self, 'parent_node_kls', self.__class__)
        return tuple(kls(abspath(pjoin(self.path, x)))
            for x in data)

    @load_property("package.provided")
    def pkg_provided(self, data):
        return split_negations(data, cpv.versioned_CPV)

    @load_property("virtuals")
    def virtuals(self, data):
        d = {}
        for line in data:
            l = line.split()
            if len(l) != 2:
                raise ValueError("%r is malformated" % line)
            d[cpv.CPV.unversioned(l[0]).package] = self.eapi_atom(l[1])
        return mappings.ImmutableDict(d)

    @load_property("package.mask")
    def masks(self, data):
        return split_negations(data, self.eapi_atom)

    @load_property("deprecated", handler=None, fallback=None)
    def deprecated(self, data):
        if data is not None:
            data = iter(data)
            try:
                replacement = compatibility.next(data).strip()
                msg = "\n".join(x.lstrip("#").strip()
                    for x in data)
                data = (replacement, msg)
            except StopIteration:
                # only an empty replacement could trigger this; thus
                # formatted badly.
                raise ValueError("didn't specify a replacement profile")
        return data

    def _parse_package_use(self, data):
        d = mappings.defaultdict(list)
        # split the data down ordered cat/pkg lines
        for line in data:
            l = line.split()
            a = self.eapi_atom(l[0])
            if len(l) == 1:
                raise Exception("malformed line- %r" % (line,))
            d[a.key].append(chunked_data(a,
                *split_negations(l[1:])))

        return mappings.ImmutableDict((k, _build_cp_atom_payload(v, atom.atom(k)))
            for k,v in d.iteritems())

    @load_property("package.use.force")
    def pkg_use_force(self, data):
        return self._parse_package_use(data)

    @load_property("package.use.mask")
    def pkg_use_mask(self, data):
        return self._parse_package_use(data)

    @load_property("package.use")
    def pkg_use(self, data):
        c = ChunkedDataDict()
        c.update_from_stream(
            chain_from_iterable(self._parse_package_use(data).itervalues()))
        c.freeze()
        return c

    @load_property("use.force")
    def forced_use(self, data):
        c = ChunkedDataDict()
        neg, pos = split_negations(data)
        if neg or pos:
            c.add_bare_global(neg, pos)
        c.update_from_stream(
            chain_from_iterable(self.pkg_use_force.itervalues()))
        c.freeze()
        return c

    @load_property("use.mask")
    def masked_use(self, data):
        c = ChunkedDataDict()
        neg, pos = split_negations(data)
        if neg or pos:
            c.add_bare_global(neg, pos)
        c.update_from_stream(
            chain_from_iterable(self.pkg_use_mask.itervalues()))
        c.freeze()
        return c

    @load_property('make.defaults', fallback=None, read_func=_open_utf8,
        handler=None)
    def default_env(self, data):
        rendered = _make_incrementals_dict()
        for parent in self.parents:
            rendered.update(parent.default_env.iteritems())

        if data is not None:
            data = read_bash_dict(data, vars_dict=rendered)
            rendered.update(data.iteritems())
        return mappings.ImmutableDict(rendered)

    @klass.jit_attr
    def bashrc(self):
        path = pjoin(self.path, "profile.bashrc")
        if os.path.exists(path):
            return local_source(path)
        return None

    @load_property('eapi', fallback=('0',))
    def eapi_obj(self, data):
        data = [x.strip() for x in data]
        data = filter(None, data)
        if len(data) != 1:
            raise ProfileError(self.path, 'eapi', "multiple lines detected")
        elif not (data[0].isdigit() and int(data[0]) in const.eapi_capable):
            raise ProfileError(self.path, 'eapi', 'unsupported eapi: %s' % data[0])
        return get_eapi(data[0])

    eapi = klass.alias_attr("eapi_obj.magic")
    eapi_atom = klass.alias_attr("eapi_obj.atom_kls")


class EmptyRootNode(ProfileNode):

    __inst_caching__ = True

    parents = ()
    deprecated = None
    pkg_use = masked_use = forced_use = ChunkedDataDict()
    forced_use.freeze()
    virtuals = pkg_use_force = pkg_use_mask = mappings.ImmutableDict()
    pkg_provided = visibility = system = ((), ())


def _empty_provides_iterable(*args, **kwds):
    return iter(())

def _empty_provides_has_match(*args, **kwds):
    return False


class ProfileStack(object):

    pkgcore_config_type = ConfigHint({'profile':'str'},
        required=('profile'), typename='profile')

    _node_kls = ProfileNode

    def __init__(self, profile):
        self.profile = profile
        self.node = self._node_kls(profile)

    @property
    def arch(self):
        return self.default_env.get("ARCH")

    deprecated = klass.alias_attr("node.deprecated")

    @klass.jit_attr
    def stack(self):
        def f(node):
            for x in node.parents:
                for y in f(x):
                    yield y
            yield node

        return tuple(f(self.node))

    def _collapse_use_dict(self, attr):

        stack = [getattr(x, attr) for x in self.stack]

        d = ChunkedDataDict()
        for mapping in stack:
            d.merge(mapping)

        d.freeze()
        return d

    @klass.jit_attr
    def forced_use(self):
        return self._collapse_use_dict("forced_use")

    @klass.jit_attr
    def masked_use(self):
        return self._collapse_use_dict("masked_use")

    @klass.jit_attr
    def pkg_use(self):
        return self._collapse_use_dict("pkg_use")

    def _collapse_generic(self, attr):
        s = set()
        for node in self.stack:
            val = getattr(node, attr)
            s.difference_update(val[0])
            s.update(val[1])
        return s

    @klass.jit_attr
    def default_env(self):
        d = dict(self.node.default_env.iteritems())
        for incremental in const.incrementals:
            v = d.pop(incremental, '').split()
            if v:
                if incremental in const.incrementals_unfinalized:
                    d[incremental] = tuple(v)
                else:
                    v = misc.render_incrementals(v)
                    if v:
                        d[incremental] = tuple(v)
        return mappings.ImmutableDict(d.iteritems())

    @klass.jit_attr
    def use_expand(self):
        if "USE_EXPAND" in const.incrementals:
            return tuple(self.default_env.get("USE_EXPAND", ()))
        return tuple(self.default_env.get("USE_EXPAND", '').split())

    @klass.jit_attr
    def use_expand_hidden(self):
        if "USE_EXPAND_HIDDEN" in const.incrementals:
            return tuple(self.default_env.get("USE_EXPAND_HIDDEN", ()))
        return tuple(self.default_env.get("USE_EXPAND_HIDDEN", "").split())

    @klass.jit_attr
    def virtuals(self):
        d = {}
        for profile in self.stack:
            d.update(profile.virtuals)
        return mappings.ImmutableDict(d)

    @klass.jit_attr
    def make_virtuals_repo(self):
        return currying.partial(AliasedVirtuals, self.virtuals)

    @klass.jit_attr
    def provides_repo(self):
        d = {}
        for pkg in self._collapse_generic("pkg_provided"):
            d.setdefault(pkg.category, {}).setdefault(pkg.package,
                []).append(pkg.fullver)
        intermediate_parent = PkgProvidedParent()
        obj = util.SimpleTree(d, pkg_klass=currying.partial(PkgProvided,
            intermediate_parent), livefs=True, frozen=True)
        intermediate_parent._parent_repo = obj

        if not d:
            obj.match = obj.itermatch = _empty_provides_iterable
            obj.has_match = _empty_provides_has_match
        return obj

    @klass.jit_attr
    def masks(self):
        return frozenset(chain(self._collapse_generic("masks"),
            self._collapse_generic("visibility")))

    @klass.jit_attr
    def bashrcs(self):
        return tuple(x.bashrc for x in self.stack if x.bashrc is not None)

    bashrc = klass.alias_attr("bashrcs")
    path = klass.alias_attr("node.path")

    @klass.jit_attr
    def system(self):
        return self._collapse_generic('system')


class OnDiskProfile(ProfileStack):

    pkgcore_config_type = ConfigHint({'basepath':'str', 'profile':'str'},
        required=('basepath', 'profile'), typename='profile')

    def __init__(self, basepath, profile, load_profile_base=True):
        ProfileStack.__init__(self, pjoin(basepath, profile))
        self.basepath = basepath
        self.load_profile_base = load_profile_base

    @staticmethod
    def split_abspath(path):
        path = abspath(path)
        # filter's heavy, but it handles '/' while also
        # suppressing the leading '/'
        chunks = filter(None, path.split("/"))
        try:
            # poor mans rindex.
            pbase = max(x for x in enumerate(chunks) if x[1] == 'profiles')[0]
        except ValueError:
            # no base found.
            return None
        return pjoin("/", *chunks[:pbase+1]), '/'.join(chunks[pbase+1:])

    @classmethod
    def from_abspath(cls, path):
        vals = cls.split_abspath(path)
        if vals is not None:
            vals = cls(load_profile_base=True, *vals)
        return vals

    @klass.jit_attr
    def stack(self):
        l = ProfileStack.stack.function(self)
        if self.load_profile_base:
            l = (EmptyRootNode(self.basepath),) + l
        return l


class UserProfileNode(ProfileNode):

    parent_node_kls = ProfileNode

    def __init__(self, path, parent_path):
        self.override_path = pjoin(path, parent_path)
        ProfileNode.__init__(self, path)

    @klass.jit_attr
    def parents(self):
        return (ProfileNode(self.override_path),)


class UserProfile(OnDiskProfile):

    pkgcore_config_type = ConfigHint({'user_path':'str', 'parent_path':'str',
        'parent_profile':'str', 'incrementals':'list'},
        required=('user_path','parent_path', 'parent_profile'),
        typename='profile')

    def __init__(self, user_path, parent_path, parent_profile,
        load_profiles_base=False):
        OnDiskProfile.__init__(self, parent_path, parent_profile,
            load_profiles_base)
        self.node = UserProfileNode(user_path, pjoin(parent_path, parent_profile))


class PkgProvidedParent(object):

    def __init__(self, **kwds):
        self.__dict__.update(kwds)


class PkgProvided(ebuild_src.base):

    __slots__ = ('use',)

    package_is_real = False
    __inst_caching__ = True

    @property
    def keywords(self):
        return InvertedContains(())

    def __init__(self, *a, **kwds):
        ebuild_src.base.__init__(self, *a, **kwds)
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

    def __init__(self, virtuals, repo, *overrides):
        """
        :param virtuals: dict of virtual -> providers
        :param repo: :obj:`pkgcore.ebuild.repository.UnconfiguredTree` parent repo
        :keyword overrides: mapping of virtual pkgname -> matches to override defaults
        """
        virtual.tree.__init__(self, livefs=False)
        self._original_virtuals = virtuals
        self._overrides = tuple(overrides)
        if not overrides:
            # no point in delaying.
            self.packages._cache['virtuals'] = tuple(virtuals.iterkeys())
            self._virtuals = virtuals
        self.aliased_repo = repo
        self._versions_map = {}

    def _load_data(self):
        self._virtuals = self._delay_apply_overrides(self._original_virtuals,
            self._overrides)
        self.packages._cache['virtual'] = tuple(self._virtuals.iterkeys())

    @staticmethod
    def _delay_apply_overrides(virtuals, overrides):
        d = {}
        for vtree in overrides:
            for virt, provider in vtree.default_providers.iteritems():
                if virt in d:
                    d[virt] &= d[virt] & provider
                else:
                    d[virt] = provider

        if not d:
            return virtuals
        for k, v in d.iteritems():
            if len(v) == 1:
                d[k] = tuple(v)[0]
            else:
                d[k] = packages.OrRestriction(*v)
        virtuals = virtuals.copy()
        virtuals.update(d)
        return virtuals

    def _get_versions(self, catpkg):
        if catpkg[0] != "virtual":
            raise KeyError("no %s package in this repository" % catpkg)
        vers = set()
        for pkg in self.aliased_repo.itermatch(self._virtuals[catpkg[1]]):
            self._versions_map.setdefault(catpkg[1], {}).setdefault(pkg.fullver, []).append(
                pkg.versioned_atom)
            vers.add(pkg.fullver)
        return tuple(vers)

    def _expand_vers(self, cp, ver):
        return self._versions_map.get(cp[1], {}).get(ver, ())

    def _fetch_metadata(self, pkg):
        data = self._virtuals[pkg.package]
        if isinstance(data, atom.atom):
            data = [data]
        data = [atom.atom("=%s-%s" % (x.key, pkg.fullver)) for x in data]
        if len(data) == 1:
            return data[0]
        return packages.OrRestriction(*data)
