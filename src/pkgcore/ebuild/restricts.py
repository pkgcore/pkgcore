# "More than one statement on a single line"
# pylint: disable-msg=C0321

"""
atom version restrict
"""

__all__ = ("VersionMatch",)

from snakeoil.klass import generic_equality

from ..restrictions import packages, restriction, values
from . import cpv, errors


# TODO: change values.EqualityMatch so it supports le, lt, gt, ge, eq,
# ne ops, and convert this to it.
class _VersionMatch(restriction.base, metaclass=generic_equality):

    """
    package restriction implementing gentoo ebuild version comparison rules

    any overriding of this class *must* maintain numerical order of
    self.vals, see intersect for reason why. vals also must be a tuple.
    """

    __slots__ = ("ver", "rev", "vals", "droprev", "negate")

    __attr_comparison__ = ('negate', 'rev', 'droprev', 'vals')

    type = restriction.value_type
    attr = "fullver"

    _convert_op2str = {
        (-1,): "<",
        (-1, 0): "<=",
        (0,): "=",
        (0, 1): ">=",
        (1,): ">",
    }

    _convert_str2op = {v: k for k, v in _convert_op2str.items()}

    def __init__(self, operator, ver, rev=None, negate=False, **kwd):
        """
        :param operator: version comparison to do,
            valid operators are ('<', '<=', '=', '>=', '>', '~')
        :type operator: string
        :param ver: version to base comparison on
        :type ver: string
        :param rev: revision to base comparison on
        :type rev: None (no rev), or an int
        :param negate: should the restriction results be negated;
            currently forced to False
        """

        kwd["negate"] = False
        sf = object.__setattr__
        sf(self, "ver", ver)
        sf(self, "rev", rev)
        if operator != "~" and operator not in self._convert_str2op:
            raise errors.InvalidVersion(
                self.ver, self.rev, f"invalid operator, '{operator}'")

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

    def match(self, pkg, *args, **kwargs):
        if self.droprev:
            r1, r2 = None, None
        else:
            r1, r2 = self.rev, pkg.revision

        if pkg.version is None:
            return False

        return (cpv.ver_cmp(pkg.version, r2, self.ver, r1) in self.vals) != self.negate

    def __str__(self):
        s = self._convert_op2str[self.vals]

        if self.negate:
            n = "not "
        else:
            n = ''

        if self.droprev or not self.rev:
            return f"ver {n}{s} {self.ver}"
        return f"ver-rev {n}{s} {self.ver}-r{self.rev}"

    def __repr__(self):
        s = self._convert_op2str[self.vals]
        s += self.ver
        if self.rev:
            s += f"-r{self.rev}"
        return "<%s %s negate=%s droprrev=%s @#x>" % (
            self.__class__.__name__, s, self.negate, self.droprev)

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


class VersionMatch(packages.PackageRestriction):

    __slots__ = ()
    __inst_caching__ = True

    def __init__(self, *args, **kwds):
        v = _VersionMatch(*args, **kwds)
        super().__init__('fullver', v, negate=kwds.get('negate', False))

    def match(self, pkg, *args, **kwds):
        return self.restriction.match(pkg)


class SlotDep(packages.PackageRestriction):

    __slots__ = ()
    __inst_caching__ = True

    def __init__(self, slot, **kwds):
        v = values.StrExactMatch(slot)
        super().__init__('slot', v, negate=kwds.get('negate', False))


class SubSlotDep(packages.PackageRestriction):

    __slots__ = ()
    __inst_caching__ = True

    def __init__(self, slot, **kwds):
        v = values.StrExactMatch(slot)
        super().__init__('subslot', v, negate=kwds.get('negate', False))


class CategoryDep(packages.PackageRestriction):

    __slots__ = ()
    __inst_caching__ = True

    def __init__(self, category, negate=False):
        super().__init__('category', values.StrExactMatch(category, negate=negate))


class PackageDep(packages.PackageRestriction):

    __slots__ = ()
    __inst_caching__ = True

    def __init__(self, package, negate=False):
        super().__init__('package', values.StrExactMatch(package, negate=negate))


class RepositoryDep(packages.PackageRestriction):

    __slots__ = ()
    __inst_caching__ = True

    def __init__(self, repo_id, negate=False):
        super().__init__('repo.repo_id', values.StrExactMatch(repo_id), negate=negate)


class StaticUseDep(packages.PackageRestriction):

    __slots__ = ()
    __inst_caching__ = True

    def __init__(self, false_use, true_use):
        v = []
        if false_use:
            v.append(values.ContainmentMatch2(false_use, negate=True, match_all=True))
        if true_use:
            v.append(values.ContainmentMatch2(true_use, match_all=True))

        l = len(v)
        if l == 2:
            v = values.AndRestriction(*v)
        elif l == 1:
            v = v[0]
        else:
            v = values.AlwaysTrue

        super().__init__('use', v)


class _UseDepDefaultContainment(values.ContainmentMatch2):

    __slots__ = ('if_missing',)

    def __init__(self, if_missing, vals, negate=False):
        object.__setattr__(self, 'if_missing', bool(if_missing))
        super().__init__(vals, negate=negate, match_all=True)

    def match(self, val):
        reduced_vals = self.vals
        iuse, use = val
        if reduced_vals.issubset(iuse):
            # use normal pathways.
            return values.ContainmentMatch2.match(self, use)
        if self.if_missing == self.negate:
            # ex: if is_missing = False, missing flags are assumed falsed.
            # if negate is False, then we're not trying to disable the flags, trying to enable.
            # as such, this cannot match.  The inverse holds true.
            return False
        # to reach here, either we're trying to force all flags false and the default is False,
        # or we're trying to force all flags on, and the default is on.
        # recall that negate is unfortunately a double negative in labeling...
        reduced_vals = reduced_vals.intersection(iuse)
        if reduced_vals:
            return values.ContainmentMatch2.match(self, use, _values_override=reduced_vals)
        # nothing to match means all are missing, but the default makes them considered a match.
        return True

    def force_False(self, pkg, attr, val):
        reduced_vals = self.vals
        # see comments in .match for clarification of logic.
        iuse, use = val
        if reduced_vals.issubset(iuse):
            return values.ContainmentMatch2.force_False(self, pkg, 'use', use)
        if self.if_missing == self.negate:
            return False
        reduced_vals = reduced_vals.intersection(iuse)
        if reduced_vals:
            return values.ContainmentMatch2.force_False(self, pkg, 'use', use, reduced_vals)
        return True

    def force_True(self, pkg, attr, val):
        reduced_vals = self.vals
        # see comments in .match for clarification of logic.
        iuse, use = val
        if reduced_vals.issubset(iuse):
            return values.ContainmentMatch2.force_True(self, pkg, 'use', use)
        if self.if_missing == self.negate:
            return False
        reduced_vals = reduced_vals.intersection(iuse)
        if reduced_vals:
            return values.ContainmentMatch2.force_True(self, pkg, 'use', use, reduced_vals)
        return True


class UseDepDefault(packages.PackageRestrictionMulti):

    __slots__ = ()
    __inst_caching__ = True

    def __init__(self, if_missing, false_use, true_use):
        v = []
        if false_use:
            v.append(_UseDepDefaultContainment(if_missing, false_use, negate=True))
        if true_use:
            v.append(_UseDepDefaultContainment(if_missing, true_use))

        l = len(v)
        if l == 2:
            v = values.AndRestriction(*v)
        elif l == 1:
            v = v[0]
        else:
            v = values.AlwaysTrue

        super().__init__(('iuse', 'use'), v)


def _parse_nontransitive_use(sequence):
    default_off = [[], []]
    default_on = [[], []]
    normal = [[], []]
    for token in sequence:
        if token[-1] == ')':
            if token[-2] == '+':
                trg = default_on
            else:
                trg = default_off
            token = token[:-3]
        else:
            trg = normal
        if token[0] == '-':
            trg[0].append(token[1:])
        else:
            trg[1].append(token)

    r = []
    default_off = (tuple(default_off[0]), tuple(default_off[1]))
    default_on = (tuple(default_on[0]), tuple(default_on[1]))
    normal = (tuple(normal[0]), tuple(normal[1]))
    if normal[0] or normal[1]:
        r.append(StaticUseDep(*normal))
    if default_off[0] or default_off[1]:
        r.append(UseDepDefault(False, *default_off))
    if default_on[0] or default_on[1]:
        r.append(UseDepDefault(True, *default_on))
    return r
