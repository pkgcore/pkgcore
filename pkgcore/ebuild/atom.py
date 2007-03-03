# Copyright: 2005-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

# "More than one statement on a single line"
# pylint: disable-msg=C0321

"""
gentoo ebuild atom, should be generalized into an agnostic base
"""

from pkgcore.util.klass import generic_equality
from pkgcore.restrictions import values, packages, boolean
from pkgcore.util.compatibility import all
from pkgcore.ebuild import cpv, errors
from pkgcore.ebuild.atom_restricts import VersionMatch
from pkgcore.util.demandload import demandload
demandload(globals(),
    "pkgcore.restrictions.delegated:delegate "
    "pkgcore.util.currying:partial "
)

# namespace compatibility...
MalformedAtom = errors.MalformedAtom

valid_use_chars = set(str(x) for x in xrange(10))
valid_use_chars.update(chr(x) for x in xrange(ord("a"), ord("z")))
valid_use_chars.update(chr(x) for x in xrange(ord("A"), ord("Z")))
valid_use_chars.update(["_", ".", "+", "-"])
valid_use_chars = frozenset(valid_use_chars)

def native_init(self, atom, negate_vers=False):
    """
    @param atom: string, see gentoo ebuild atom syntax
    """
    sf = object.__setattr__

    orig_atom = atom

    u = atom.find("[")
    if u != -1:
        # use dep
        u2 = atom.find("]", u)
        if u2 == -1:
            raise errors.MalformedAtom(atom,
                "use restriction isn't completed")
        sf(self, "use", tuple(sorted(atom[u+1:u2].split(','))))
        for x in self.use:
            if not all(y in valid_use_chars for y in x):
                raise errors.MalformedAtom(atom,
                    "invalid char spotted in use dep")
        if not all(x.rstrip("-") for x in self.use):
            raise errors.MalformedAtom(
                atom, "cannot have empty use deps in use restriction")
        atom = atom[0:u]+atom[u2 + 1:]
    else:
        sf(self, "use", None)
    s = atom.find(":")
    if s != -1:
        i2 = atom.find(":", s + 1)
        if i2 != -1:
            repo_id = atom[i2 + 1:]
            if not repo_id:
                raise errors.MalformedAtom(atom,
                    "repo_id must not be empty")
            elif ":" in repo_id:
                raise errors.MalformedAtom(atom,
                    "repo_id may contain only [a-Z0-9_.-+/]")
            atom = atom[:i2]
            sf(self, "repo_id", repo_id)
        else:
            sf(self, "repo_id", None)
        # slot dep.
        slots = tuple(sorted(atom[s+1:].split(",")))
        if not all(slots):
            # if the slot char came in only due to repo_id, force slots to None
            if len(slots) == 1 and i2 != -1:
                slots = None
            else:
                raise errors.MalformedAtom(atom,
                    "empty slots aren't allowed")
        sf(self, "slot", slots)
        atom = atom[:s]
    else:
        sf(self, "slot", None)
        sf(self, "repo_id", None)
    del u, s

    sf(self, "blocks", atom[0] == "!")
    if self.blocks:
        atom = atom[1:]

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

    try:
        c = cpv.CPV(self.cpvstr)
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
    elif self.version is not None:
        raise errors.MalformedAtom(orig_atom,
            'versioned atom requires an operator')
    sf(self, "hash", hash(orig_atom))
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
        r.insert(0, packages.PackageRestriction("repo.repo_id",
            values.StrExactMatch(self.repo_id)))

    if self.fullver is not None:
        if self.op == '=*':
            r.append(packages.PackageRestriction(
                    "fullver", values.StrGlobMatch(self.fullver)))
        else:
            r.append(VersionMatch(self.op, self.version, self.revision,
                                  negate=self.negate_vers))

    if self.slot is not None:
        if len(self.slot) == 1:
            v = values.StrExactMatch(self.slot[0])
        else:
            v = values.OrRestriction(*map(values.StrExactMatch,
                self.slot))
        r.append(packages.PackageRestriction("slot", v))

    if self.use is not None:
        false_use = [x[1:] for x in self.use if x[0] == "-"]
        true_use = [x for x in self.use if x[0] != "-"]
        v = []
        if false_use:
            v.append(values.ContainmentMatch(negate=True,
                all=True, *false_use))

        if true_use:
            v.append(values.ContainmentMatch(all=True, *true_use))
        if len(v) == 1:
            v = v[0]
        else:
            v = values.AndRestriction(*v)
        r.append(packages.PackageRestriction("use", v))

    r = tuple(r)
    object.__setattr__(self, attr, r)
    return r


native_atom_overrides = {"__init__":native_init,
    "__getattr__":native__getattr__}

try:
    from pkgcore.ebuild._atom import overrides as atom_overrides
except ImportError:
    atom_overrides = native_atom_overrides


class atom(boolean.AndRestriction):

    """Currently implements gentoo ebuild atom parsing.

    Should be converted into an agnostic dependency base.
    """

    __slots__ = (
        "blocks", "op", "negate_vers", "cpvstr", "use",
        "slot", "hash", "category", "version", "revision", "fullver",
        "package", "key", "repo_id")

    type = packages.package_type
    negate = False

    __attr_comparison__ = ("cpvstr", "op", "blocks", "negate_vers",
        "use", "slot")

    __metaclass__ = generic_equality
    __inst_caching__ = True

    locals().update(atom_overrides.iteritems())

    def __repr__(self):
        atom = self.op + self.cpvstr
        if self.blocks:
            atom = '!' + atom
        attrs = [atom]
        if self.use:
            attrs.append('use=' + repr(self.use))
        if self.slot:
            attrs.append('slot=' + repr(self.slot))
        return '<%s %s @#%x>' % (
            self.__class__.__name__, ' '.join(attrs), id(self))

    def __reduce__(self):
        return (atom, (str(self), self.negate_vers))

    def iter_dnf_solutions(self, full_solution_expansion=False):
        if full_solution_expansion:
            return boolean.AndRestriction.iter_dnf_solutions(
                self, full_solution_expansion=True)
        return iter([[self]])

    def cnf_solutions(self, full_solution_expansion=False):
        if full_solution_expansion:
            return boolean.AndRestriction.cnf_solutions(
                self, full_solution_expansion=True)
        return [[self]]

    def __str__(self):
        if self.op == '=*':
            s = "=%s*" %  self.cpvstr
        else:
            s = self.op + self.cpvstr
        if self.blocks:
            s = "!" + s
        if self.use:
            s += "[%s]" % ",".join(self.use)
        if self.slot:
            s += ":%s" % ",".join(self.slot)
            if self.repo_id:
                s += ":%s" % self.repo_id
        elif self.repo_id:
            s += "::%s" % self.repo_id
        return s

    def __hash__(self):
        return self.hash

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

        c = cmp(self.negate_vers, other.negate_vers)
        if c:
            return c

        c = cmp(self.slot, other.slot)
        if c:
            return c

        return cmp(self.use, other.use)

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
            return VersionMatch(
                other.op, other.version, other.revision).match(self)
        if other.op == '=':
            if self.op == '=*':
                return other.fullver.startswith(self.fullver)
            return VersionMatch(
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
                VersionMatch(
                    other.op, other.version, other.revision).match(ranged) and
                VersionMatch(
                    ranged.op, ranged.version, ranged.revision).match(other))

        if other.op == '~':
            # Other definitely matches its own version. If ranged also
            # does we're done:
            if VersionMatch(
                ranged.op, ranged.version, ranged.revision).match(other):
                return True
            # The only other case where we intersect is if ranged is a
            # > or >= on other's version and a nonzero revision. In
            # that case other will match ranged. Be careful not to
            # give a false positive for ~2 vs <2 here:
            return ranged.op in ('>', '>=') and VersionMatch(
                other.op, other.version, other.revision).match(ranged)

        if other.op == '=*':
            # The fun one, since glob matches do not correspond to a
            # single contiguous region of versions.

            # a glob match definitely matches its own version, so if
            # ranged does too we're done:
            if VersionMatch(
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


def split_atom(inst):
    if len(inst.restrictions) > 3:
        a = packages.AndRestriction(*inst.restrictions[2:])
    elif len(inst.restrictions) == 3:
        a = inst.restrictions[2]
    else:
        a = []
    return inst.category + "/" + inst.package, a

def _collapsed_restrict_match(data, pkg, mode):
    # mode is ignored; non applicable.
    for r in data.get(pkg.key, ()):
        if r.match(pkg):
            return True
    return False

def generate_collapsed_restriction(atoms, negate=False):
    d = {}
    for a in atoms:
        d.setdefault(a.key, []).append(a)
    return delegate(partial(_collapsed_restrict_match, d), negate=negate)
