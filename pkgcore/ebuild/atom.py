# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

# "More than one statement on a single line"
# pylint: disable-msg=C0321

"""
gentoo ebuild atom, should be generalized into an agnostic base
"""

from pkgcore.restrictions import values, packages, boolean, restriction
from pkgcore.util.compatibility import all
from pkgcore.ebuild import cpv
from pkgcore.package import errors
from pkgcore.util.demandload import demandload
demandload(globals(), "pkgcore.restrictions.delegated:delegate ")

class MalformedAtom(errors.InvalidDependency):

    def __init__(self, atom, err=''):
        errors.InvalidDependency.__init__(
            self, "atom '%s' is malformed: error %s" % (atom, err))
        self.atom, self.err = atom, err


class InvalidVersion(errors.InvalidDependency):

    def __init__(self, ver, rev, err=''):
        errors.InvalidDependency.__init__(
            self,
            "Version restriction ver='%s', rev='%s', is malformed: error %s" %
            (ver, rev, err))
        self.ver, self.rev, self.err = ver, rev, err


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


class atom(boolean.AndRestriction):

    """Currently implements gentoo ebuild atom parsing.

    Should be converted into an agnostic dependency base.
    """

    __slots__ = (
        "glob", "blocks", "op", "negate_vers", "cpvstr", "use",
        "slot", "hash", "category", "version", "revision", "fullver",
        "package", "key")

    type = packages.package_type

    __inst_caching__ = True

    def __init__(self, atom, negate_vers=False):
        """
        @param atom: string, see gentoo ebuild atom syntax
        """
        boolean.AndRestriction.__init__(self)

        sf = object.__setattr__

        atom = orig_atom = atom.strip()
        sf(self, "hash", hash(atom))

        sf(self, "blocks", atom[0] == "!")
        if self.blocks:
            pos = 1
        else:
            pos = 0

        if atom[pos] in ('<', '>'):
            if atom[pos + 1] == '=':
                pos += 2
            else:
                pos += 1
        elif atom[pos] in ('~', '='):
            pos += 1

        if self.blocks:
            sf(self, "op", atom[1:pos])
        else:
            sf(self, "op", atom[:pos])

        u = atom.find("[")
        if u != -1:
            # use dep
            u2 = atom.find("]", u)
            if u2 == -1:
                raise MalformedAtom(atom, "use restriction isn't completed")
            sf(self, "use", tuple(x.strip() for x in atom[u+1:u2].split(',')))
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

        if atom[-1] == '*':
            if self.op != '=':
                raise MalformedAtom(
                    orig_atom, "range operators on a range are nonsencial, "
                    "drop the globbing or use =cat/pkg* or !=cat/pkg*, not %s"
                    % self.op)
            sf(self, "glob", True)
            sf(self, "cpvstr", atom[pos:-1])
            # may have specified a period to force calculation
            # limitation there- hence rstrip'ing it for the cpv
            # generation
        else:
            sf(self, "glob", False)
            sf(self, "cpvstr", atom[pos:])

        c = cpv.CPV(self.cpvstr)
        sf(self, "key", c.key)
        sf(self, "package", c.package)
        sf(self, "category", c.category)
        sf(self, "version", c.version)
        sf(self, "fullver", c.fullver)
        sf(self, "revision", c.revision)

        sf(self, "negate_vers", negate_vers)
        if "~" == self.op:
            if self.version is None:
                raise MalformedAtom(orig_atom, "~ operator requires a version")
        # force jitting of it.
        object.__delattr__(self, "restrictions")

    def __repr__(self):
        atom = self.op + self.cpvstr
        if self.blocks:
            atom = '!' + atom
        if self.glob:
            atom = atom + '*'
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
                if self.glob:
                    r.append(packages.PackageRestriction(
                            "fullver", values.StrGlobMatch(self.fullver)))
                else:
                    r.append(VersionMatch(self.op, self.version, self.revision,
                                          negate=self.negate_vers))
            elif self.op:
                raise MalformedAtom(
                    str(self),
                    "cannot specify a version operator without a version")

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
                r.append(packages.PackageRestriction(
                        "slot", values.StrExactMatch(self.slot)))
            object.__setattr__(self, attr, tuple(r))
            return r

        raise AttributeError(attr)

    def __str__(self):
        if self.blocks:
            s = "!%s%s" % (self.op, self.cpvstr)
        else:
            s = self.op + self.cpvstr
        if self.glob:
            s += "*"
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
        c = cpv.ver_cmp(self.version, self.revision,
                        other.version, other.revision)
        if c:
            return c

        return cmp(self.op, other.op)

    def __ne__(self, other):
        return self is not other

    def __eq__(self, other):
        return self is other


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
