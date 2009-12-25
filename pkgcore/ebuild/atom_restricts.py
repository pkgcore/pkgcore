# Copyright: 2005-2009 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

# "More than one statement on a single line"
# pylint: disable-msg=C0321

"""
atom version restrict
"""

from pkgcore.restrictions import packages, restriction
from pkgcore.ebuild import cpv, errors
from snakeoil.klass import generic_equality
from snakeoil.compatibility import is_py3k

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
    __metaclass__ = generic_equality
    __attr_comparison__ = ('negate', 'rev', 'droprev', 'vals')

    type = packages.package_type
    attr = "fullver"

    _convert_op2str = {(-1,):"<", (-1, 0): "<=", (0,):"=",
        (0, 1):">=", (1,):">"}

    _convert_str2op = dict([(v, k) for k, v in _convert_op2str.iteritems()])
    if not is_py3k:
        del k, v

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
        sf = object.__setattr__
        sf(self, "ver", ver)
        sf(self, "rev", rev)
        if operator != "~" and operator not in self._convert_str2op:
            raise errors.InvalidVersion(self.ver, self.rev,
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

    def __repr__(self):
        s = self._convert_op2str[self.vals]
        s += self.ver
        if self.rev:
            s += "-r%s" % (self.rev,)
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
