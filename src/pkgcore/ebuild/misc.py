"""
misc. stuff we've not found a spot for yet.
"""

__all__ = (
    "ChunkedDataDict", "IncrementalsDict", "PayloadDict",
    "chunked_data", "collapsed_restrict_to_data", "incremental_chunked",
    "incremental_expansion", "incremental_expansion_license",
    "non_incremental_collapsed_restrict_to_data", "optimize_incrementals",
    "sort_keywords",
)

from collections import defaultdict, namedtuple
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from itertools import chain

from snakeoil import mappings
from snakeoil.klass import alias_method, generic_equality
from snakeoil.sequences import iflatten_instance

from ..restrictions import boolean, packages, restriction
from . import atom

restrict_payload = namedtuple("restrict_data", ["restrict", "data"])
chunked_data = namedtuple("chunked_data", ("key", "neg", "pos"))


def sort_keywords(keywords):
    """Sort keywords in the proper order: i.e. glob-arches, arch, prefix-arches."""
    def _sort_kwds(kw):
        parts = tuple(reversed(kw.lstrip('~-').partition('-')))
        return parts[0], parts[2]
    return sorted(keywords, key=_sort_kwds)


def optimize_incrementals(sequence):
    # roughly the algorithm walks sequences right->left,
    # identifying terminal points for incrementals; aka, -x x, 'x'
    # is the terminal point- no point in having -x.
    finalized = set()
    for item in reversed(sequence):
        if item[0] == '-':
            i = item[1:]
            if not i:
                raise ValueError("encountered an incomplete negation (just -, no flag)")
            if i == '*':
                # seen enough.
                yield item
                return
            if i not in finalized:
                finalized.add(i)
                yield item
        else:
            if item not in finalized:
                yield item
                finalized.add(item)


def incremental_chunked(orig, iterables):
    for cinst in iterables:
        orig.difference_update(cinst.neg)
        orig.update(cinst.pos)


def incremental_expansion(iterable, orig=None, msg_prefix='', finalize=True):
    if orig is None:
        orig = set()

    for token in iterable:
        if token[0] == '-':
            i = token[1:]
            if not i:
                raise ValueError(
                    f"{msg_prefix} encountered an incomplete negation, '-'")
            if i == '*':
                orig.clear()
            else:
                orig.discard(i)
            if not finalize:
                orig.add(token)
        else:
            orig.discard("-" + token)
            orig.add(token)

    return orig


def incremental_expansion_license(pkg, licenses, license_groups, iterable, msg_prefix=''):
    seen = set()
    for token in iterable:
        if token[0] == '-':
            i = token[1:]
            if not i:
                raise ValueError(
                    f"{pkg}: {msg_prefix}encountered an incomplete negation, '-'")
            if i == '*':
                seen.clear()
            else:
                if i[0] == '@':
                    i = i[1:]
                    if not i:
                        raise ValueError(
                            f"{pkg}: {msg_prefix}encountered an incomplete negation"
                            " of a license group, '-@'")
                    seen.difference_update(license_groups.get(i, ()))
                else:
                    seen.discard(i)
        elif token[0] == '@':
            i = token[1:]
            if not i:
                raise ValueError(
                    f"{pkg}: {msg_prefix}encountered an incomplete license group, '@'")
            seen.update(license_groups.get(i, ()))
        elif token == '*':
            seen.update(licenses)
        else:
            seen.add(token)
    return seen


class IncrementalsDict(mappings.DictMixin):

    disable_py3k_rewriting = True

    def __init__(self, incrementals, **kwds):
        self._incrementals = incrementals
        self._dict = {}
        super().__init__(**kwds)

    def __setitem__(self, key, value):
        if key in self._incrementals:
            if key in self._dict:
                self._dict[key] += f' {value}'
            else:
                self._dict[key] = value
        else:
            self._dict[key] = value

    for x in "getitem delitem len iter".split():
        x = f'__{x}__'
        locals()[x] = alias_method(f"_dict.{x}")
    s = "pop clear keys items values"
    for x in s.split():
        locals()[x] = alias_method(f"_dict.{x}")
    del x, s


class collapsed_restrict_to_data(metaclass=generic_equality):

    __attr_comparison__ = ('defaults', 'freeform', 'atoms', '__class__')
    incremental = True

    def __init__(self, *restrict_sources, **kwds):
        """
        descriptive, no?

        Basically splits an iterable of restrict:data into
        level of specificity, repo, cat, pkg, atom (dict) for use
        in filters

        Finally, a finalize_defaults kwd is supported to control whether
        incremental_expansion finalizes the initial defaults list.
        defaults to True.
        """

        always = []
        repo = []
        cat = []
        pkg = []
        multi = []
        atom_d = {}
        for restrict_pairs in restrict_sources:
            for a, data in restrict_pairs:
                if not data:
                    continue
                if isinstance(a, restriction.AlwaysBool):
                    # yes, odd attr name, but negate holds the val to return.
                    # note also, we're dropping AlwaysFalse; it'll never match.
                    if a.negate:
                        always.extend(data)
                        for atomlist in atom_d.values():
                            atomlist.append(
                                (a, set([flag for flag in data if flag.startswith("-")])))
                elif isinstance(a, atom.atom):
                    atom_d.setdefault(a.key, []).append((a, data))
                elif isinstance(a, boolean.AndRestriction):
                    multi.append((a, data))
                elif isinstance(a, packages.PackageRestriction):
                    if a.attr == "category":
                        cat.append((a, data))
                    elif a.attr == "package":
                        pkg.append((a, data))
                    elif a.attr == "repo.repo_id":
                        repo.append((a, data))
                    else:
                        raise ValueError(
                            f"{a!r} doesn't operate on "
                            f"package/category/repo: data {data!r}")
                else:
                    raise ValueError(
                        f"{a!r} is not an AlwaysBool, PackageRestriction, "
                        f"or atom: data {data!r}")

        if always:
            always = incremental_expansion(always, finalize=kwds.get("finalize_defaults", True))
        else:
            always = set()
        self.defaults = always
        self.defaults_finalized = set(x for x in self.defaults if not x.startswith("-"))
        self.freeform = tuple(x for x in (repo, cat, pkg, multi) if x)
        self.atoms = atom_d

    def pull_data(self, pkg, force_copy=False, pre_defaults=()):
        l = []
        for specific in self.freeform:
            for restrict, data in specific:
                if restrict.match(pkg):
                    l.append(data)
        for atom, data in self.atoms.get(pkg.key, ()):
            if atom.match(pkg):
                l.append(data)

        if pre_defaults:
            s = set(pre_defaults)
            incremental_expansion(self.defaults, orig=s)
        else:
            s = set(self.defaults_finalized)

        if l:
            incremental_expansion(iflatten_instance(l), orig=s)
        return s

    def iter_pull_data(self, pkg, pre_defaults=()):
        for item in pre_defaults:
            yield item
        for item in self.defaults:
            yield item
        for specific in self.freeform:
            for restrict, data in specific:
                if restrict.match(pkg):
                    for item in data:
                        yield item
        for atom, data in self.atoms.get(pkg.key, ()):
            if atom.match(pkg):
                for item in data:
                    yield item


class non_incremental_collapsed_restrict_to_data(collapsed_restrict_to_data):

    def pull_data(self, pkg, force_copy=False):
        l = []
        for specific in self.freeform:
            for restrict, data in specific:
                if restrict.match(pkg):
                    l.append(data)
        for atom, data in self.atoms.get(pkg.key, ()):
            if atom.match(pkg):
                l.append(data)
        if not l:
            if force_copy:
                return set(self.defaults)
            return self.defaults
        s = set(self.defaults)
        s.update(iflatten_instance(l))
        return s

    def iter_pull_data(self, pkg):
        l = [self.defaults]
        for specific in self.freeform:
            l.extend(data for restrict, data in specific if restrict.match(pkg))
        for atom, data in self.atoms.get(pkg.key, ()):
            if atom.match(pkg):
                l.append(data)
        if len(l) == 1:
            return iter(self.defaults)
        return iflatten_instance(l)


def _cached_build_cp_atom_payload(cache, sequence, restrict, payload_form=False):
    sequence = list(sequence)
    key = (payload_form, restrict, tuple(sequence))
    val = cache.get(key)
    if val is None:
        val = cache[key] = _build_cp_atom_payload(sequence, restrict, payload_form=payload_form)
    return val


def _build_cp_atom_payload(sequence, restrict, payload_form=False):
    locked = {}
    ldefault = locked.setdefault

    l = []

    if payload_form:
        def f(r, neg, pos):
            return restrict_payload(r, tuple(chain(('-' + x for x in neg), pos)))
    else:
        f = chunked_data

    i = list(sequence)
    if len(i) <= 1:
        if not i:
            return ()
        return (f(i[0].key, i[0].neg, i[0].pos),)

    i = reversed(i)

    for data in i:
        if data.key == packages.AlwaysTrue or getattr(data.key, 'is_simple', False):
            for n in data.neg:
                ldefault(n, False)
            for p in data.pos:
                ldefault(p, True)
            continue
        neg = tuple(x for x in data.neg if x not in locked)
        pos = tuple(x for x in data.pos if x not in locked)
        if neg or pos:
            l.append((data.key, neg, pos))

    # thus far we've done essentially a tracing for R->L, of globals,
    # this leaves d-u/a X, =d-u/a-1 X # slipping through however,
    # since the specific is later.  Plus it's reversed from what we want.
    # so we rebuild, but apply the same global trick as we go.

    if not locked:
        # all is specific/non-simple, just reverse and return
        return tuple(f(*vals) for vals in reversed(l))

    new_l = [f(
        restrict,
        tuple(k for k, v in locked.items() if not v),  # neg
        tuple(k for k, v in locked.items() if v)  # pos
    )]
    # we exploit a few things this time around in reusing the algo from above
    # we know there is only going to be one global (which we just added),
    # and that everything is specific.

    lget = locked.get

    for key, neg, pos in reversed(l):
        # only grab the deltas; if a + becomes a specific -
        neg = tuple(x for x in neg if lget(x, True))
        pos = tuple(x for x in pos if not lget(x, False))
        if neg or pos:
            new_l.append(f(key, neg, pos))

    return tuple(new_l)


class ChunkedDataDict(metaclass=generic_equality):

    __attr_comparison__ = ('_global_settings', '_dict')

    def __init__(self):
        self._global_settings = []
        self._dict = defaultdict(partial(list, self._global_settings))

    @property
    def frozen(self):
        return isinstance(self._dict, mappings.ImmutableDict)

    def clone(self, unfreeze=False):
        obj = self.__class__()
        if self.frozen and not unfreeze:
            obj._dict = self._dict
            obj._global_settings = self._global_settings
            return obj
        obj._dict = defaultdict(partial(list, self._global_settings))
        for key, values in self._dict.items():
            obj._dict[key].extend(values)
        obj._global_settings = list(self._global_settings)
        return obj

    def mk_item(self, key, neg, pos):
        return chunked_data(key, tuple(neg), tuple(pos))

    def add_global(self, item):
        return self._add_global(item.neg, item.pos, restrict=item.key)

    def add_bare_global(self, disabled, enabled):
        return self._add_global(disabled, enabled)

    def _add_global(self, disabled, enabled, restrict=None):
        if not disabled and not enabled:
            return
        # discard current global in the mapping.
        disabled = set(disabled)
        enabled = set(enabled)
        if restrict is None:
            restrict = packages.AlwaysTrue
        payload = self.mk_item(restrict, tuple(disabled), tuple(enabled))
        for vals in self._dict.values():
            vals.append(payload)

        self._expand_globals([payload])

    def merge(self, cdict):
        if not isinstance(cdict, ChunkedDataDict):
            raise TypeError(
                "merge expects a ChunkedDataDict instance; "
                f"got type {type(cdict)}, {cdict!r}")
        if isinstance(cdict, PayloadDict) and not isinstance(self, PayloadDict):
            raise TypeError(
                "merge expects a PayloadDataDict instance; "
                f"got type {type(cdict)}, {cdict!r}")
        # straight extensions for this, rather than update_from_stream.
        d = self._dict
        for key, values in cdict._dict.items():
            d[key].extend(values)

        # note the cdict we're merging has the globals layer through it already, ours
        # however needs to have the new globals appended to all untouched keys
        # (no need to update the merged keys- they already have that global data
        # interlaced)
        new_globals = cdict._global_settings
        if new_globals:
            updates = set(d)
            updates.difference_update(cdict._dict)
            for key in updates:
                d[key].extend(new_globals)
            self._expand_globals(new_globals)

    def _expand_globals(self, new_globals):
        # while a chain seems obvious here, reversed is used w/in _build_cp_atom;
        # reversed doesn't like chain, so we just modify the list and do it this way.
        self._global_settings.extend(new_globals)
        restrict = getattr(new_globals[0], 'key', packages.AlwaysTrue)
        if restrict == packages.AlwaysTrue:
            self._global_settings[:] = list(
                _build_cp_atom_payload(self._global_settings, restrict))

    def add(self, cinst):
        self.update_from_stream([cinst])

    def update_from_stream(self, stream):
        for cinst in stream:
            if getattr(cinst.key, 'key', None) is not None:
                # atom, or something similar.  use the key lookup.
                # hack also... recreate the restriction; this is due to
                # internal idiocy in ChunkedDataDict that will be fixed.
                new_globals = (x for x in self._global_settings
                               if x not in self._dict[cinst.key.key])
                self._dict[cinst.key.key].extend(new_globals)
                self._dict[cinst.key.key].append(cinst)
            else:
                self.add_global(cinst)

    def freeze(self):
        if not isinstance(self._dict, mappings.ImmutableDict):
            self._dict = mappings.ImmutableDict(
                (k, tuple(v))
                for k, v in self._dict.items())
            self._global_settings = tuple(self._global_settings)

    def optimize(self, cache=None):
        if cache is None:
            d_stream = (
                (k, _build_cp_atom_payload(v, atom.atom(k), False))
                for k, v in self._dict.items())
            g_stream = (_build_cp_atom_payload(
                self._global_settings,
                packages.AlwaysTrue, payload_form=isinstance(self, PayloadDict)))
        else:
            d_stream = ((k, _cached_build_cp_atom_payload(
                cache, v, atom.atom(k), False))
                for k, v in self._dict.items())
            g_stream = (_cached_build_cp_atom_payload(
                cache, self._global_settings,
                packages.AlwaysTrue, payload_form=isinstance(self, PayloadDict)))

        if self.frozen:
            self._dict = mappings.ImmutableDict(d_stream)
            self._global_settings = tuple(g_stream)
        else:
            self._dict.update(d_stream)
            self._global_settings[:] = list(g_stream)

    def render_to_dict(self):
        d = dict(self._dict)
        if self._global_settings:
            d[packages.AlwaysTrue] = self._global_settings[:]
        return d

    def render_to_payload(self):
        d = PayloadDict()
        d = {atom.atom(k): _build_cp_atom_payload(v, atom.atom(k), True)
             for k, v in self._dict.items()}
        if self._global_settings:
            data = _build_cp_atom_payload(
                self._global_settings,
                packages.AlwaysTrue, payload_form=True)
            d[packages.AlwaysTrue] = tuple(data)
        return d

    def __bool__(self):
        return bool(self._global_settings) or bool(self._dict)

    def __str__(self):
        return str(self.render_to_dict())

    def render_pkg(self, pkg, pre_defaults=()):
        items = self._dict.get(pkg.key)
        if items is None:
            items = self._global_settings
        s = set(pre_defaults)
        incremental_chunked(s, (cinst for cinst in items if cinst.key.match(pkg)))
        return s

    pull_data = render_pkg


class PayloadDict(ChunkedDataDict):

    def mk_item(self, key, neg, pos):
        return restrict_payload(key, tuple(chain(("-" + x for x in neg), pos)))

    def add_bare_global(self, payload):
        neg = [x[1:] for x in payload if x[0] == '-']
        pos = [x for x in payload if x[0] != '-']
        ChunkedDataDict.add_bare_global(self, neg, pos)

    def add_global(self, pinst):
        neg = [x[1:] for x in pinst.data if x[0] == '-']
        pos = [x for x in pinst.data if x[0] != '-']
        return ChunkedDataDict.add_global(self, chunked_data(pinst.restrict, neg, pos))

    def update_from_stream(self, stream):
        for pinst in stream:
            if getattr(pinst.restrict, 'key', None) is not None:
                # atom, or something similar.  use the key lookup.
                # hack also... recreate the restriction; this is due to
                # internal idiocy in ChunkedDataDict that will be fixed.
                self._dict[pinst.restrict.key].append(pinst)
            else:
                self.add_global(pinst)

    def render_pkg(self, pkg, pre_defaults=()):
        items = self._dict.get(atom.atom(pkg.key))
        if items is None:
            items = self._global_settings
        s = set(pre_defaults)
        data = chain.from_iterable(
            item.data for item in items if item.restrict.match(pkg))
        return incremental_expansion(data, orig=s)

    pull_data = render_pkg


def run_sanity_checks(pkgs, domain, threads=None):
    """Run all sanity checks for a sequence of packages."""
    failures = defaultdict(list)
    sanity_check = lambda pkg_ops: pkg_ops.sanity_check()

    # generator of pkgs supporting sanity checks
    def _filter_pkgs(pkgs):
        for pkg in pkgs:
            pkg_ops = domain.pkg_operations(pkg)
            if pkg_ops.supports("sanity_check"):
                yield pkg_ops

    with ThreadPoolExecutor(max_workers=threads) as executor:
        for pkg, failed in executor.map(sanity_check, _filter_pkgs(pkgs)):
            if failed:
                failures[pkg].extend(failed)
    return failures
