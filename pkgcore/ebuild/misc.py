# Copyright: 2005-2010 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
misc. stuff we've not found a spot for yet.
"""

__all__ = ("optimize_incrementals", "incremental_expansion_license",
    "collapsed_restrict_to_data", "non_incremental_collapsed_restrict_to_data"
    )


from pkgcore.restrictions import packages, restriction
from pkgcore.ebuild.atom import atom

from snakeoil.lists import iflatten_instance
from snakeoil.klass import generic_equality
from snakeoil.sequences import namedtuple

from itertools import chain

from snakeoil.currying import partial
from snakeoil.demandload import demandload

demandload(globals(),
    'pkgcore.ebuild.atom:atom',
    'pkgcore.restrictions:packages',
    'snakeoil.mappings:defaultdict,ImmutableDict',
)


restrict_payload = namedtuple("restrict_data", ["restrict", "data"])
chunked_data = namedtuple("chunked_data", ("key", "neg", "pos"))

def split_negations(data, func=str):
    neg, pos = [], []
    for line in data:
        if line[0] == '-':
            if len(line) == 1:
                raise ValueError("'-' negation without a token")
            neg.append(func(line[1:]))
        else:
            pos.append(func(line))
    return (tuple(neg), tuple(pos))

def optimize_incrementals(sequence):
    # roughly the algorithm walks sequences right->left,
    # identifying terminal points for incrementals; aka, -x x, 'x'
    # is the terminal point- no point in having -x.
    finalized = set()
    result = []
    for item in reversed(sequence):
        if item[0] == '-':
            i = item[1:]
            if not i:
                raise ValueError("%sencountered an incomplete negation, '-'"
                    % (msg_prefix,))
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


def native_incremental_expansion(orig, iterable, msg_prefix='', finalize=True):
    for token in iterable:
        if token[0] == '-':
            i = token[1:]
            if not i:
                raise ValueError("%sencountered an incomplete negation, '-'"
                    % (msg_prefix,))
            if i == '*':
                orig.clear()
            else:
                orig.discard(i)
            if not finalize:
                orig.add(token)
        else:
            orig.discard("-" + token)
            orig.add(token)

try:
    from pkgcore.ebuild._misc import incremental_expansion
except ImportError:
    incremental_expansion = native_incremental_expansion

def incremental_expansion_license(licenses, license_groups, iterable, msg_prefix=''):
    seen = set()
    for token in iterable:
        if token[0] == '-':
            i = token[1:]
            if not i:
                raise ValueError("%sencountered an incomplete negation, '-'"
                    % (msg_prefix,))
            if i == '*':
                seen.clear()
            else:
                if i[0] == '@':
                    i = i[1:]
                    if not i:
                        raise ValueError("%sencountered an incomplete negation"
                            " of a license group, '-@'"
                                % (msg_prefix,))
                    seen.difference_update(license_groups.get(i, ()))
                else:
                    seen.discard(i)
        elif token[0] == '@':
            i = token[1:]
            if not i:
                raise ValueError("%sencountered an incomplete license group"
                    ", '@'" % (msg_prefix,))
            seen.update(license_groups.get(i, ()))
        elif token == '*':
            seen.update(licenses)
        else:
            seen.add(token)
    return seen

class collapsed_restrict_to_data(object):

    __metaclass__ = generic_equality
    __attr_comparison__ = ('defaults', 'freeform', 'atoms', '__class__')

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
                        for atomlist in atom_d.itervalues():
                            atomlist.append((a, set([flag for flag in data if flag.startswith("-")])))
                elif isinstance(a, atom):
                    atom_d.setdefault(a.key, []).append((a, data))
                elif isinstance(a, packages.PackageRestriction):
                    if a.attr == "category":
                        cat.append((a, data))
                    elif a.attr == "package":
                        pkg.append((a, data))
                    else:
                        raise ValueError("%r doesn't operate on package/category: "
                            "data %r" % (a, data))
                else:
                    raise ValueError("%r is not a AlwaysBool, PackageRestriction, "
                        "or atom: data %r" % (a, data))

        if always:
            s = set()
            incremental_expansion(s, always,
                finalize=kwds.get("finalize_defaults", True))
            always = s
        else:
            always = set()
        self.defaults = always
        self.defaults_finalized = set(x for x in self.defaults
            if not x.startswith("-"))
        self.freeform = tuple(x for x in (repo, cat, pkg) if x)
        self.atoms = atom_d

    def atom_intersects(self, atom):
        return atom.key in self.atoms

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
            incremental_expansion(s, self.defaults)
        else:
            s = set(self.defaults_finalized)

        if l:
            incremental_expansion(s, iflatten_instance(l))
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


def _build_cp_atom_payload(sequence, restrict, payload_form=False, initial_on=None):

    atrue = packages.AlwaysTrue

    locked = {}
    ldefault = locked.setdefault

    l = []

    if payload_form:
        def f(r, neg, pos):
            return restrict_payload(r,
                tuple(chain(('-' + x for x in neg), pos)))
    else:
        f = chunked_data

    i = reversed(sequence)

    if initial_on:
        i = chain(chunked_data(atrue, (), initial_on), i)

    for data in i:
        if data.key == atrue or data.key.is_simple:
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

    new_l = [f(restrict,
        tuple(k for k,v in locked.iteritems() if not v), #neg
        tuple(k for k,v in locked.iteritems() if v) #pos
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


class ChunkedDataDict(object):

    def __init__(self, initial_mapping=None, freeze=False):
        self._global_settings = []
        self._dict = defaultdict(partial(list, self._global_settings))
        if initial_mapping:
            self.update_from_mapping(initial_mapping)
        if freeze:
            self.freeze()

    def update_from_mapping(self, mapping):
        atrue = packages.AlwaysTrue
        global_settings = mapping.get(atrue)
        if global_settings:
            for val in global_settings:
                self._add_global_item(val)
        for key, vals in mapping.iteritems():
            if key == atrue:
                continue
            self.add_specific_direct(key, *vals)

    def mk_item(self, key, neg, pos):
        return chunked_data(key, tuple(neg), tuple(pos))

    def _add_global_item(self, item):
        return self.add_global(item.neg, item.pos, restrict=item.key)

    def add_global(self, disabled, enabled, restrict=None):
        if not disabled and not enabled:
            return
        global_settings = self._global_settings
        # discard current global in the mapping.
        disabled = set(disabled)
        enabled = set(enabled)
        if restrict is None:
            restrict = packages.AlwaysTrue
        payload = self.mk_item(restrict, tuple(disabled), tuple(enabled))
        for vals in self._dict.itervalues():
            vals.append(payload)

        self._global_settings.append(payload)


    def add_specific_chunk(self, atom_inst, disabled, enabled):
        self._dict[atom_inst].append(self.mk_item(atom_inst, disabled, enabled))

    def add_specific_direct(self, key, *chunks):
        self._dict[key].extend(chunks)

    def freeze(self):
        if not isinstance(self._dict, ImmutableDict):
            self._dict = ImmutableDict((k, tuple(v))
                for k,v in self._dict.iteritems())
            self._global_settings = tuple(self._global_settings)

    def optimize(self):
        d = dict((atom(k), _build_cp_atom_payload(v, atom(k), False))
            for k,v in self._dict.iteritems())
        if isinstance(self._dict, ImmutableDict):
            d = ImmutableDict(d)
        if self._global_settings:
            self._global_settings[:] = list(_build_cp_atom_payload(self._global_settings,
                packages.AlwaysTrue, payload_form=isinstance(self, PayloadDict)))
        self._dict = d

    def render_to_payload(self):
        d = PayloadDict()
        d = dict((atom(k), _build_cp_atom_payload(v, atom(k), True))
            for k,v in self._dict.iteritems())
        if self._global_settings:
            data = _build_cp_atom_payload(self._global_settings,
                packages.AlwaysTrue, payload_form=True)
            d[packages.AlwaysTrue] = tuple(data)
        return d


class PayloadDict(ChunkedDataDict):

    def mk_item(self, key, neg, pos):
        return restrict_payload(key,
            tuple(chain(("-" + x for x in neg), pos)))

    def add_global(self, payload, restrict=None):
        neg = [x[1:] for x in payload if x[0] == '-']
        pos = [x for x in payload if x[0] != '-']
        ChunkedDataDict.add_global(self, neg, pos, restrict=restrict)

    def _add_global_item(self, item):
        return self.add_global(item.data, restrict=item.restrict)

    def update_from_stream(self, stream):
        for item in stream:
            if hasattr(item.restrict, 'key'):
               self.add_specific_direct(item.restrict, item)
            else:
               self.add_global(item.data, restrict=item.restrict)

    def update_from_mapping(self, mapping):
        stream = mapping.iteritems()

        for key, items in stream:
            if hasattr(key, 'key'):
                self.add_specific_direct(key, *items)
            else:
                for item in items:
                    self.add_global(item.data, restrict=item.restrict)

        if isinstance(mapping, PayloadDict):
            for item in mapping._global_settings:
                self.add_global(item.data, restrict=item.restrict)

    def render_pkg(self, pkg, pre_defaults=()):
        items = self._dict.get(atom(pkg.key))
        if items is None:
            items = self._global_settings
        s = set(pre_defaults)
        incremental_expansion(s,
            chain.from_iterable(item.data for item in items
                if item.restrict.match(pkg)))
        return s

    pull_data = render_pkg
