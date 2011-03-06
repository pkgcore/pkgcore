# Copyright: 2005-2010 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

# "More than one statement on a single line"
# pylint: disable-msg=C0321

"""
gentoo ebuild atom, should be generalized into an agnostic base
"""

__all__ = ("atom", "transitive_use_atom", "generate_collapsed_restriction")

import string
from pkgcore.restrictions import values, packages, boolean
from pkgcore.ebuild import cpv, errors, const, atom_restricts
from pkgcore.ebuild import atom_restricts
from snakeoil.compatibility import all, is_py3k, cmp
from snakeoil.klass import (generic_equality, inject_richcmp_methods_from_cmp,
    reflective_hash)
from snakeoil.demandload import demandload
from snakeoil.currying import partial
demandload(globals(),
    "pkgcore.restrictions.delegated:delegate",
    'pkgcore.restrictions.packages:Conditional,AndRestriction@PkgAndRestriction',
    'pkgcore.restrictions.values:ContainmentMatch',
)

# namespace compatibility...
MalformedAtom = errors.MalformedAtom

alphanum = set(string.digits)
if is_py3k:
    alphanum.update(string.ascii_letters)
else:
    alphanum.update(string.letters)

valid_repo_chars = set(alphanum)
valid_repo_chars.update("_-")
valid_use_chars = set(alphanum)
valid_use_chars.update("@+_-")
valid_slot_chars = set(alphanum)
valid_slot_chars.update(".+_-")
alphanum = frozenset(alphanum)
valid_use_chars = frozenset(valid_use_chars)
valid_repo_chars = frozenset(valid_repo_chars)
valid_slot_chars = frozenset(valid_slot_chars)

def native_init(self, atom, negate_vers=False, eapi=-1):
    """
    :param atom: string, see gentoo ebuild atom syntax
    :keyword negate_vers: boolean controlling whether the version should be
        inverted for restriction matching
    :keyword eapi: string/int controlling what eapi to enforce for this atom
    """
    sf = object.__setattr__

    orig_atom = atom

    override_kls = False
    use_start = atom.find("[")
    slot_start = atom.find(":")
    if use_start != -1:
        # use dep
        use_end = atom.find("]", use_start)
        if use_end == -1:
            raise errors.MalformedAtom(orig_atom,
                "use restriction isn't completed")
        elif use_end != len(atom) -1:
            raise errors.MalformedAtom(orig_atom,
                "trailing garbage after use dep")
        sf(self, "use", tuple(sorted(atom[use_start + 1:use_end].split(','))))
        for x in self.use:
            # stripped purely for validation reasons
            try:
                if x[-1] in "=?":
                    override_kls = True
                    x = x[:-1]
                    if x[0] == '!':
                        x = x[1:]
                    if x[0] == '-':
                        raise errors.MalformedAtom(orig_atom,
                            "malformed use flag: %s" % x)
                elif x[0] == '-':
                    x = x[1:]

                if x[-1] == ')' and eapi not in (0, 1, 2, 3):
                    # use defaults.
                    if x[-3:] in ("(+)", "(-)"):
                        x = x[:-3]

                if not x:
                    raise errors.MalformedAtom(orig_atom,
                        'empty use dep detected')
                elif x[0] not in alphanum:
                    raise errors.MalformedAtom(orig_atom,
                        "invalid first char spotted in use dep '%s' (must be alphanumeric)" % x)
                if not valid_use_chars.issuperset(x):
                    raise errors.MalformedAtom(orig_atom,
                        "invalid char spotted in use dep '%s'" % x)
            except IndexError:
                raise errors.MalformedAtom(orig_atom,
                    'empty use dep detected')
        if override_kls:
            sf(self, '__class__', self._transitive_use_atom)
        atom = atom[0:use_start]+atom[use_end + 1:]
    else:
        sf(self, "use", None)
    if slot_start != -1:
        i2 = atom.find("::", slot_start)
        if i2 != -1:
            repo_id = atom[i2 + 2:]
            if not repo_id:
                raise errors.MalformedAtom(orig_atom,
                    "repo_id must not be empty")
            elif repo_id[0] in '-':
                raise errors.MalformedAtom(orig_atom,
                    "invalid first char of repo_id '%s' (must not begin with a hyphen)" % repo_id)
            elif not valid_repo_chars.issuperset(repo_id):
                raise errors.MalformedAtom(orig_atom,
                    "repo_id may contain only [a-Z0-9_-/], found %r" % (repo_id,))
            atom = atom[:i2]
            sf(self, "repo_id", repo_id)
        else:
            sf(self, "repo_id", None)
        # slot dep.
        slots = tuple(sorted(atom[slot_start+1:].split(",")))
        if not all(slots):
            # if the slot char came in only due to repo_id, force slots to None
            if len(slots) == 1 and i2 != -1:
                slots = None
            else:
                raise errors.MalformedAtom(orig_atom,
                    "empty slots aren't allowed")
        else:
            for x in slots:
                if x[0] in '-.':
                    raise errors.MalformedAtom(orig_atom,
                        "invalid first char of slot dep '%s' (must not begin with a hyphen or a dot)" % x)
                if not valid_slot_chars.issuperset(x):
                   raise errors.MalformedAtom(orig_atom,
                       "invalid char spotted in slot dep '%s'" % x)

        sf(self, "slot", slots)
        atom = atom[:slot_start]
    else:
        sf(self, "slot", None)
        sf(self, "repo_id", None)

    sf(self, "blocks", atom[0] == "!")
    if self.blocks:
        atom = atom[1:]
        # hackish/slow, but lstrip doesn't take a 'prune this many' arg
        # open to alternatives
        if eapi not in (0,1) and atom.startswith("!"):
            atom = atom[1:]
            sf(self, "blocks_strongly", True)
        else:
            sf(self, "blocks_strongly", False)
    else:
        sf(self, "blocks_strongly", False)

    if atom[0] in ('<', '>'):
        if atom[1] == '=':
            sf(self, 'op', atom[:2])
            atom = atom[2:]
        else:
            sf(self, 'op', atom[0])
            atom = atom[1:]
    elif atom[0] == '=':
        if atom[-1] == '*':
            sf(self, 'op', '=*')
            atom = atom[1:-1]
        else:
            atom = atom[1:]
            sf(self, 'op', '=')
    elif atom[0] == '~':
        sf(self, 'op', '~')
        atom = atom[1:]
    else:
        sf(self, 'op', '')
    sf(self, 'cpvstr', atom)

    if eapi == 0:
        for x in ('use', 'slot'):
            if getattr(self, x) is not None:
                raise errors.MalformedAtom(orig_atom,
                    "%s atoms aren't supported for eapi 0" % x)
    elif eapi == 1:
        if self.use is not None:
            raise errors.MalformedAtom(orig_atom,
                "use atoms aren't supported for eapi < 2")
    if eapi != -1:
        if self.repo_id is not None:
            raise errors.MalformedAtom(orig_atom,
                "repo_id atoms aren't supported for eapi %i" % eapi)
        if self.slot and len(self.slot) > 1:
            raise errors.MalformedAtom(orig_atom,
                "multiple slot restrictions not supported for eapi %s" % eapi)
    if use_start != -1 and slot_start != -1 and use_start < slot_start:
        raise errors.MalformedAtom(orig_atom,
            "slot restriction must proceed use")
    try:
        c = cpv.CPV(self.cpvstr, versioned=bool(self.op))
    except errors.InvalidCPV, e:
        raise errors.MalformedAtom(orig_atom, str(e))
    sf(self, "key", c.key)
    sf(self, "package", c.package)
    sf(self, "category", c.category)
    sf(self, "version", c.version)
    sf(self, "fullver", c.fullver)
    sf(self, "revision", c.revision)

    if self.op:
        if self.version is None:
            raise errors.MalformedAtom(orig_atom,
                "operator requires a version")
        elif self.op == '~' and self.revision:
            raise errors.MalformedAtom(orig_atom,
                "~ revision operater cannot be combined with a revision")
    elif self.version is not None:
        raise errors.MalformedAtom(orig_atom,
            'versioned atom requires an operator')
    sf(self, "_hash", hash(orig_atom))
    sf(self, "negate_vers", negate_vers)


def native__getattr__(self, attr):
    if attr != "restrictions":
        raise AttributeError(attr)

    # ordering here matters; against 24702 ebuilds for
    # a non matchable atom with package as the first restriction
    # 10 loops, best of 3: 206 msec per loop
    # with category as the first(the obvious ordering)
    # 10 loops, best of 3: 209 msec per loop
    # why?  because category is more likely to collide;
    # at the time of this profiling, there were 151 categories.
    # over 11k packages however.
    r = [packages.PackageRestriction(
            "package", values.StrExactMatch(self.package)),
        packages.PackageRestriction(
            "category", values.StrExactMatch(self.category))]

    if self.repo_id is not None:
        r.insert(0, atom_restricts.RepositoryDep(self.repo_id))

    if self.fullver is not None:
        if self.op == '=*':
            r.append(packages.PackageRestriction(
                    "fullver", values.StrGlobMatch(self.fullver)))
        else:
            r.append(atom_restricts.VersionMatch(self.op, self.version, self.revision,
                                  negate=self.negate_vers))

    if self.slot is not None:
        r.append(atom_restricts.SlotDep(*self.slot))

    if self.use is not None:
        false_use = [x[1:] for x in self.use if x[0] == "-"]
        true_use = [x for x in self.use if x[0] != "-"]

        r.append(atom_restricts.StaticUseDep(false_use, true_use))

    r = tuple(r)
    object.__setattr__(self, attr, r)
    return r


native_atom_overrides = {"__init__":native_init,
    "__getattr__":native__getattr__}

try:
    from pkgcore.ebuild._atom import overrides as atom_overrides

    # python issue 4230 complicates things pretty heavily since
    # __getattr__ either supports descriptor or doesn't.
    # so we test it.
    class test(object):
        __getattr__ = atom_overrides['__getattr__desc']

    try:
        test().asdf
    except TypeError:

        # function was invoked incorrectly- self and attr were passed in
        # to the meth_o variant.  meaning no __getattr__ descriptor support.

        try:
            class test2(object):
                __getattr__ = atom_overrides['__getattr__nondesc']
            test2().asdf

        except SystemError:
            # ...or there was a screwup in the cpy implementation and it's
            # bitching about the passed in 'attr' key being the wrong type.
            # retrigger the exception.
            test().asdf

        except AttributeError:
            # old form works.  See the 'else' for why we do this
            atom_overrides['__getattr__'] = atom_overrides['__getattr__nondesc']

        del test2

    except AttributeError:
        # function invocation succeeded, but blew up due to our test object
        # missing expected attributes.  This is fine- it was invocable at
        # least.  Means this python version doesn't support descriptor for
        # __getattr__
        pass
    atom_overrides.setdefault('__getattr__', atom_overrides['__getattr__desc'])
    del atom_overrides['__getattr__desc']
    del atom_overrides['__getattr__nondesc']
    del test

except ImportError:
    atom_overrides = native_atom_overrides


class atom(boolean.AndRestriction):

    """Currently implements gentoo ebuild atom parsing.

    Should be converted into an agnostic dependency base.
    """

    # note we don't need _hash
    __slots__ = (
        "blocks", "blocks_strongly", "op", "cpvstr", "negate_vers",
        "use", "slot", "category", "version", "revision", "fullver",
        "package", "key", "repo_id", "_hash")

    type = packages.package_type

    negate = False

    __attr_comparison__ = ("cpvstr", "op", "blocks", "negate_vers",
        "use", "slot", "repo_id")

    inject_richcmp_methods_from_cmp(locals())
    # hack; combine these 2 metaclasses at some point...
    locals().pop("__eq__", None)
    locals().pop("__ne__", None)
    __metaclass__ = generic_equality
    __inst_caching__ = True

    locals().update(atom_overrides.iteritems())

    # overrided in child class if it's supported
    evaluate_depset = None

    @property
    def blocks_temp_ignorable(self):
        return not self.blocks_strongly

    def __repr__(self):
        if self.op == '=*':
            atom = "=%s*" %  self.cpvstr
        else:
            atom = self.op + self.cpvstr
        if self.blocks:
            atom = '!' + atom
        if self.blocks:
            if self.blocks_strongly:
                atom = '!!' + atom
            else:
                atom = '!' + atom
        attrs = [atom]
        if self.use:
            attrs.append('use=' + repr(self.use))
        if self.slot:
            attrs.append('slot=' + repr(self.slot))
        if self.repo_id:
            attrs.append('repoid=' + repr(self.repo_id))
        return '<%s %s @#%x>' % (
            self.__class__.__name__, ' '.join(attrs), id(self))

    def __reduce__(self):
        return (atom, (str(self), self.negate_vers))

    def iter_dnf_solutions(self, full_solution_expansion=False):
        if full_solution_expansion:
            return boolean.AndRestriction.iter_dnf_solutions(self, True)
        return iter([[self]])

    def iter_cnf_solutions(self, full_solution_expansion=False):
        if full_solution_expansion:
            return boolean.AndRestriction.iter_cnf_solutions(self, True)
        return iter([[self]])

    def cnf_solutions(self, full_solution_expansion=False):
        if full_solution_expansion:
            return boolean.AndRestriction.cnf_solutions(self, True)
        return [[self]]

    @property
    def is_simple(self):
        return len(self.restrictions) == 2

    def __str__(self):
        if self.op == '=*':
            s = "=%s*" %  self.cpvstr
        else:
            s = self.op + self.cpvstr
        if self.blocks:
            if self.blocks_strongly:
                s = '!!' + s
            else:
                s = '!' + s
        if self.slot:
            s += ":%s" % ",".join(self.slot)
        if self.repo_id:
            s += "::%s" % self.repo_id
        if self.use:
            s += "[%s]" % ",".join(self.use)
        return s

    __hash__ = reflective_hash('_hash')

    def __iter__(self):
        return iter(self.restrictions)

    def __getitem__(self, index):
        return self.restrictions[index]

    def __cmp__(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError("other isn't of %s type, is %s" %
                            (self.__class__, other.__class__))

        c = cmp(self.category, other.category)
        if c:
            return c

        c = cmp(self.package, other.package)
        if c:
            return c

        c = cmp(self.op, other.op)
        if c:
            return c

        c = cpv.ver_cmp(self.version, self.revision,
                        other.version, other.revision)
        if c:
            return c

        c = cmp(self.blocks, other.blocks)
        if c:
            # invert it; cmp(True, False) == 1
            # want non blockers then blockers.
            return -c

        c = cmp(self.blocks_strongly, other.blocks_strongly)
        if c:
            # want !! prior to !
            return c

        c = cmp(self.negate_vers, other.negate_vers)
        if c:
            return c

        c = cmp(self.slot, other.slot)
        if c:
            return c

        c = cmp(self.use, other.use)
        if c:
            return c

        return cmp(self.repo_id, other.repo_id)

    def intersects(self, other):
        """Check if a passed in atom "intersects" this restriction's atom.

        Two atoms "intersect" if a package can be constructed that
        matches both:
          - if you query for just "dev-lang/python" it "intersects" both
            "dev-lang/python" and ">=dev-lang/python-2.4"
          - if you query for "=dev-lang/python-2.4" it "intersects"
            ">=dev-lang/python-2.4" and "dev-lang/python" but not
            "<dev-lang/python-2.3"

        USE and slot deps are also taken into account.

        The block/nonblock state of the atom is ignored.
        """
        # Our "key" (cat/pkg) must match exactly:
        if self.key != other.key:
            return False
        # Slot dep only matters if we both have one. If we do they
        # must be identical:
        if (self.slot is not None and other.slot is not None and
            self.slot != other.slot):
            return False

        if (self.repo_id is not None and other.repo_id is not None and
            self.repo_id != other.repo_id):
            return False

        # Use deps are similar: if one of us forces a flag on and the
        # other forces it off we do not intersect. If only one of us
        # cares about a flag it is irrelevant.

        # Skip the (very common) case of one of us not having use deps:
        if self.use and other.use:
            # Set of flags we do not have in common:
            flags = set(self.use) ^ set(other.use)
            for flag in flags:
                # If this is unset and we also have the set version we fail:
                if flag[0] == '-' and flag[1:] in flags:
                    return False

        # Remaining thing to check is version restrictions. Get the
        # ones we can check without actual version comparisons out of
        # the way first.

        # If one of us is unversioned we intersect:
        if not self.op or not other.op:
            return True

        # If we are both "unbounded" in the same direction we intersect:
        if (('<' in self.op and '<' in other.op) or
            ('>' in self.op and '>' in other.op)):
            return True

        # Trick used here: just use the atoms as sufficiently
        # package-like object to pass to these functions (all that is
        # needed is a version and revision attr).

        # If one of us is an exact match we intersect if the other matches it:
        if self.op == '=':
            if other.op == '=*':
                return self.fullver.startswith(other.fullver)
            return atom_restricts.VersionMatch(
                other.op, other.version, other.revision).match(self)
        if other.op == '=':
            if self.op == '=*':
                return other.fullver.startswith(self.fullver)
            return atom_restricts.VersionMatch(
                self.op, self.version, self.revision).match(other)

        # If we are both ~ matches we match if we are identical:
        if self.op == other.op == '~':
            return (self.version == other.version and
                    self.revision == other.revision)

        # If we are both glob matches we match if one of us matches the other.
        if self.op == other.op == '=*':
            return (self.fullver.startswith(other.fullver) or
                    other.fullver.startswith(self.fullver))

        # If one of us is a glob match and the other a ~ we match if the glob
        # matches the ~ (ignoring a revision on the glob):
        if self.op == '=*' and other.op == '~':
            return other.fullver.startswith(self.version)
        if other.op == '=*' and self.op == '~':
            return self.fullver.startswith(other.version)

        # If we get here at least one of us is a <, <=, > or >=:
        if self.op in ('<', '<=', '>', '>='):
            ranged, other = self, other
        else:
            ranged, other = other, self

        if '<' in other.op or '>' in other.op:
            # We are both ranged, and in the opposite "direction" (or
            # we would have matched above). We intersect if we both
            # match the other's endpoint (just checking one endpoint
            # is not enough, it would give a false positive on <=2 vs >2)
            return (
                atom_restricts.VersionMatch(
                    other.op, other.version, other.revision).match(ranged) and
                atom_restricts.VersionMatch(
                    ranged.op, ranged.version, ranged.revision).match(other))

        if other.op == '~':
            # Other definitely matches its own version. If ranged also
            # does we're done:
            if atom_restricts.VersionMatch(
                ranged.op, ranged.version, ranged.revision).match(other):
                return True
            # The only other case where we intersect is if ranged is a
            # > or >= on other's version and a nonzero revision. In
            # that case other will match ranged. Be careful not to
            # give a false positive for ~2 vs <2 here:
            return ranged.op in ('>', '>=') and atom_restricts.VersionMatch(
                other.op, other.version, other.revision).match(ranged)

        if other.op == '=*':
            # The fun one, since glob matches do not correspond to a
            # single contiguous region of versions.

            # a glob match definitely matches its own version, so if
            # ranged does too we're done:
            if atom_restricts.VersionMatch(
                ranged.op, ranged.version, ranged.revision).match(other):
                return True
            if '<' in ranged.op:
                # Remaining cases where this intersects: there is a
                # package smaller than ranged.fullver and
                # other.fullver that they both match.

                # If other.revision is not None then other does not
                # match anything smaller than its own fullver:
                if other.revision is not None:
                    return False

                # If other.revision is None then we can always
                # construct a package smaller than other.fullver by
                # tagging e.g. an _alpha1 on, since
                # cat/pkg_beta2_alpha1_alpha1 is a valid version.
                # (Yes, really. Try it if you don't believe me.)
                # If and only if other also matches ranged then
                # ranged will also match one of those smaller packages.
                # XXX (I think, need to try harder to verify this.)
                return ranged.fullver.startswith(other.version)
            else:
                # Remaining cases where this intersects: there is a
                # package greater than ranged.fullver and
                # other.fullver that they both match.

                # We can always construct a package greater than
                # other.fullver by adding a digit to it.
                # If and only if other also matches ranged then
                # ranged will match such a larger package
                # XXX (I think, need to try harder to verify this.)
                return ranged.fullver.startswith(other.version)

        # Handled all possible ops.
        raise NotImplementedError(
            'Someone added an op to atom without adding it to intersects')

    def f(cls, *args, **kwds):
        return cls(*args, **kwds)

    for x in const.eapi_capable:
        locals()['eapi%i_atom' % x] = classmethod(partial(f, eapi=x))

    del f, x



class transitive_use_atom(atom):

    __slots__ = ()
    __inst_caching__ = True
    _nontransitive_use_atom = atom

    is_simple = False

    def _stripped_use(self):
        return str(self).split("[", 1)[0]

    @staticmethod
    def _mk_conditional(flag, payload, negate=False):
        return Conditional('use', ContainmentMatch(flag, negate=negate),
            payload)

    def _recurse_transitive_use_conds(self, atom_str, forced_use, varied):
        if not varied:
            s = ','.join(forced_use)
            if s:
               s = '[%s]' % s
            return (self._nontransitive_use_atom(atom_str + s), )

        flag = varied[0]
        use = flag.lstrip('!').rstrip('?=')
        varied = varied[1:]
        l = []
        if flag[-1] == '?':
            # a[x?] == x? ( a[x] ) !x? ( a )
            # a[!x?] == x? ( a ) !x? ( a[-x] )
            if flag[0] != '!':
                return (self._mk_conditional(use,
                        self._recurse_transitive_use_conds(atom_str,
                            forced_use + [use], varied)),
                    self._mk_conditional(use,
                        self._recurse_transitive_use_conds(atom_str,
                            forced_use, varied), negate=True)
                    )
            return (self._mk_conditional(use,
                    self._recurse_transitive_use_conds(atom_str,
                        forced_use, varied)),
                self._mk_conditional(use,
                    self._recurse_transitive_use_conds(atom_str,
                        forced_use + ['-' + use], varied), negate=True)
                )
        # a[x=] == x? ( a[x] ) !x? ( a[-x] )
        # a[!x=] == x? ( a[-x] ) !x? ( a[x] )
        if flag[0] != '!':
            use_states = [[use], ['-' + use]]
        else:
            use_states = [['-' + use], [use]]

        return (self._mk_conditional(use,
                self._recurse_transitive_use_conds(atom_str,
                    forced_use + use_states[0], varied)),
            self._mk_conditional(use,
                self._recurse_transitive_use_conds(atom_str,
                    forced_use + use_states[1], varied), negate=True)
            )

    def __getattr__(self, attr):
        if attr != 'restrictions':
            return atom.__getattr__(self, attr)
        obj = self.convert_to_conditionals()
        object.__setattr__(self, 'restrictions', obj)
        return obj

    def convert_to_conditionals(self):
        static_use = [use for use in self.use if use[-1] not in '?=']
        variable = [use for use in self.use if use[-1] in '?=']
        return PkgAndRestriction(*
            self._recurse_transitive_use_conds(self._stripped_use(),
                static_use, variable))

    iter_dnf_solutions = boolean.AndRestriction.iter_dnf_solutions
    cnf_solutions = boolean.AndRestriction.cnf_solutions


atom._transitive_use_atom = transitive_use_atom

def _collapsed_restrict_match(data, pkg, mode):
    # mode is ignored; non applicable.
    for r in data.get(pkg.key, ()):
        if r.match(pkg):
            return True
    return False

def generate_collapsed_restriction(atoms, negate=False):
    d = {}
    for a in atoms:
        k = a.key
        if k not in d:
            d[k] = [a]
        else:
            d[k].append(a)
    return delegate(partial(_collapsed_restrict_match, d), negate=negate)
