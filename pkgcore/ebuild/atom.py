# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

# "More than one statement on a single line"
# pylint: disable-msg=C0321

"""
gentoo ebuild atom, should be generalized into an agnostic base
"""

from pkgcore.restrictions import values, packages, boolean, restriction
from pkgcore.util.compatibility import all
from pkgcore.ebuild import cpv, cpv_errors
from pkgcore.util.demandload import demandload
demandload(globals(), "pkgcore.restrictions.delegated:delegate "
    "pkgcore.ebuild.atom_errors:MalformedAtom,InvalidVersion "
)


# TODO: change values.EqualityMatch so it supports le, lt, gt, ge, eq,
# ne ops, and convert this to it.

class VersionMatch(restriction.base):

    """
    package restriction implementing gentoo ebuild version comparison rules

    any overriding of this class *must* maintain numerical order of
    self.vals, see intersect for reason why. vals also must be a tuple.
    """

    __slots__ = ("ver", "rev", "vals", "droprev", "negate")

    __inst_caching__ = True
    type = packages.package_type
    attr = "fullver"

    _convert_op2str = {(-1,):"<", (-1,0): "<=", (0,):"=",
        (0, 1):">=", (1,):">"}

    _convert_str2op = dict([(v,k) for k,v in _convert_op2str.iteritems()])    
    del k,v
    
    def __init__(self, operator, ver, rev=None, negate=False, **kwd):
        """
        @param operator: version comparison to do,
            valid operators are ('<', '<=', '=', '>=', '>', '~')
        @type operator: string
        @param ver: version to base comparison on
        @type ver: string
        @param rev: revision to base comparison on
        @type rev: None (no rev), or an int
        @param negate: should the restriction results be negated;
            currently forced to False
        """

        kwd["negate"] = False
        super(self.__class__, self).__init__(**kwd)
        sf = object.__setattr__
        sf(self, "ver", ver)
        sf(self, "rev", rev)
        if operator != "~" and operator not in self._convert_str2op:
            raise InvalidVersion(self.ver, self.rev,
                                 "invalid operator, '%s'" % operator)

        sf(self, "negate", negate)
        if operator == "~":
            if ver is None:
                raise ValueError(
                    "for ~ op, version must be something other then None")
            sf(self, "droprev", True)
            sf(self, "vals", (0,))
        else:
            sf(self, "droprev", False)
            sf(self, "vals", self._convert_str2op[operator])

    def match(self, pkginst):
        if self.droprev:
            r1, r2 = None, None
        else:
            r1, r2 = self.rev, pkginst.revision

        return (cpv.ver_cmp(pkginst.version, r2, self.ver, r1) in self.vals) \
            != self.negate

    def __str__(self):
        s = self._convert_op2str[self.vals]

        if self.negate:
            n = "not "
        else:
            n = ''

        if self.droprev or self.rev is None:
            return "ver %s%s %s" % (n, s, self.ver)
        return "ver-rev %s%s %s-r%s" % (n, s, self.ver, self.rev)

    @staticmethod
    def _convert_ops(inst):
        if inst.negate:
            if inst.droprev:
                return inst.vals
            return tuple(sorted(set((-1, 0, 1)).difference(inst.vals)))
        return inst.vals

    def __eq__(self, other):
        if self is other:
            return True
        if isinstance(other, self.__class__):
            if self.droprev != other.droprev or self.ver != other.ver \
                or self.rev != other.rev:
                return False
            return self._convert_ops(self) == self._convert_ops(other)

        return False

    def __hash__(self):
        return hash((self.droprev, self.ver, self.rev, self.negate, self.vals))


def native_parse_atom(self, atom):
    sf = object.__setattr__

    orig_atom = atom

    u = atom.find("[")
    if u != -1:
        # use dep
        u2 = atom.find("]", u)
        if u2 == -1:
            raise MalformedAtom(atom, "use restriction isn't completed")
        sf(self, "use", tuple(atom[u+1:u2].split(',')))
        if not all(x.rstrip("-") for x in self.use):
            raise MalformedAtom(
                atom, "cannot have empty use deps in use restriction")
        atom = atom[0:u]+atom[u2 + 1:]
    else:
        sf(self, "use", ())
    s = atom.find(":")
    if s != -1:
        if atom.find(":", s+1) != -1:
            raise MalformedAtom(atom, "second specification of slotting")
        # slot dep.
        sf(self, "slot", atom[s + 1:])
        if not self.slot:
            raise MalformedAtom(
                atom, "cannot have empty slot deps in slot restriction")
        atom = atom[:s]
    else:
        sf(self, "slot", None)
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
    except cpv_errors.InvalidCPV, e:
        raise MalformedAtom(orig_atom, str(e))
    sf(self, "key", c.key)
    sf(self, "package", c.package)
    sf(self, "category", c.category)
    sf(self, "version", c.version)
    sf(self, "fullver", c.fullver)
    sf(self, "revision", c.revision)

    if self.op:
        if self.version is None:
            raise MalformedAtom(orig_atom, "operator requires a version")
    elif self.version is not None:
        raise MalformedAtom(orig_atom,
                            'versioned atom requires an operator')
    sf(self, "repo_id", None)
    sf(self, "hash", hash(orig_atom))

try:
    from pkgcore.ebuild._atom import parse_atom
except ImportError:
    parse_atom = native_parse_atom

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

    __inst_caching__ = True

    def __init__(self, atom, negate_vers=False):
        """
        @param atom: string, see gentoo ebuild atom syntax
        """
#        boolean.AndRestriction.__init__(self)

        parse_atom(self, atom)
        object.__setattr__(self, "negate_vers", negate_vers)
        # force jitting of it.
        object.__delattr__(self, "restrictions")

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

    def __getattr__(self, attr):
        if attr == "restrictions":
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

            if self.version:
                if self.op == '=*':
                    r.append(packages.PackageRestriction(
                            "fullver", values.StrGlobMatch(self.fullver)))
                else:
                    r.append(VersionMatch(self.op, self.version, self.revision,
                                          negate=self.negate_vers))

            if self.use:
                false_use = [x[1:] for x in self.use if x[0] == "-"]
                true_use = [x for x in self.use if x[0] != "-"]
                if false_use:
                    # XXX: convert this to a value AndRestriction
                    # whenever harring gets off his ass and decides
                    # another round of tinkering with restriction
                    # subsystem is viable (burnt out now)
                    # ~harring
                    r.append(packages.PackageRestriction(
                            "use", values.ContainmentMatch(
                                negate=True, all=True, *false_use)))
                if true_use:
                    r.append(packages.PackageRestriction(
                            "use", values.ContainmentMatch(all=True,
                                                           *true_use)))
            if self.slot is not None:
                if len(self.slot) == 1:
                    v = values.StrExactMatch(self.slot[0])
                else:
                    v = values.OrRestriction(*map(values.StrExactMatch,
                        self.slot))
                r.append(packages.PackageRestriction("slot", v))
            object.__setattr__(self, attr, tuple(r))
            return r

        raise AttributeError(attr)

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
        
        c = cmp(self.key, other.key)
        if c:
            return c
        c = cpv.ver_cmp(self.version, self.revision,
                        other.version, other.revision)
        if c:
            return c

        if self.op == '=*':
            if other.op != '=*':
                return True
        elif other.op == '=*':
            return False

        c = cmp(self.blocks, other.blocks)
        if c:
            # invert it; cmp(True, False) == 1
            # want non blockers then blockers.
            return -c
        
        c = cmp(self.slot, other.slot)
        if c:
            return c

        c = cmp(sorted(self.use), sorted(other.use))
        if c:
            return c

        return cmp(self.op, other.op)

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
            return VersionMatch(
                other.op, other.version, other.revision).match(self)
        if other.op == '=':
            return VersionMatch(
                self.op, self.version, self.revision).match(other)

        # If we are both ~ matches we match if we are identical:
        if self.op == other.op == '~':
            return (self.version == other.version and
                    self.revision == other.revision)

        # If we are both glob matches we match if one of us matches the other.
        # (No need to check for glob, the not glob case is handled above)
        if self.op == other.op == '=*':
            return (self.fullver.startswith(other.fullver) or
                    other.fullver.startswith(self.fullver))

        # If one of us is a glob match and the other a ~ we match if the glob
        # matches the ~:
        if self.op == '=' and other.op == '~':
            return other.fullversion.startswith(self.fullversion)
        if other.op == '=' and self.op == '~':
            return self.fullversion.startswith(other.fullversion)

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
            # If both the glob and ranged itself match the ranged
            # restriction we're also done:
            if '=' in ranged.op and VersionMatch(
                other.op, other.version, other.revision).match(ranged):
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
                # If ond only if other also matches ranged then
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
    return delegate(_collapsed_restrict_match, d, negate=negate)
