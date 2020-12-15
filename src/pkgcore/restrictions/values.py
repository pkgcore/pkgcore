"""value restrictions

Works hand in hand with :obj:`pkgcore.restrictions.packages`, these
classes match against a value handed in, package restrictions pull the
attr from a package instance and hand it to their wrapped restriction
(which is a value restriction).
"""

import re

from snakeoil.klass import generic_equality, reflective_hash
from snakeoil.sequences import iflatten_instance

from . import boolean, packages, restriction


class base(restriction.base):
    """Base restriction matching object for values.

    Beware: do not check for instances of this to detect value
    restrictions! Use the C{type} attribute instead.
    """

    __slots__ = ()

    type = restriction.value_type

    def force_True(self, pkg, attr, val):
        return self.match(val)

    def force_False(self, pkg, attr, val):
        return not self.match(val)


def hashed_base(name, bases, scope):
    scope.setdefault("__hash__", reflective_hash('_hash'))
    slots = scope.get("__slots__", None)
    if slots is not None:
        if "_hash" not in slots:
            slots = scope["__slots__"] = slots + ("_hash",)
        scope.setdefault("__attr_comparison__", slots)
    return generic_equality(name, bases, scope)


class GetAttrRestriction(packages.PackageRestriction):
    """Restriction pulling an attribute and applying a child restriction."""

    __slots__ = ()
    type = restriction.value_type

    # XXX this needs further thought.
    #
    # The api for force_{True,False} is a ValueRestriction gets called
    # with a package instance, the attribute name (string), and the
    # current attribute value. We cannot really provide a child
    # restriction with a sensible pkg and a sensible attribute name,
    # so we just punt and return True/False depending on the current
    # state without "forcing" anything (default implementation in
    # "base").

    def force_True(self, pkg, attr, val):
        return self.match(val)

    def force_False(self, pkg, attr, val):
        return not self.match(val)


class VersionRestriction(base):
    """use this as base for version restrictions.

    Gives a clue to what the restriction does.
    """
    __slots__ = ()


class StrRegex(base, metaclass=hashed_base):
    """regex based matching"""

    __slots__ = ('_hash', 'flags', 'regex', '_matchfunc', 'ismatch', 'negate')
    __inst_caching__ = True

    def __init__(self, regex, case_sensitive=True, match=False, negate=False):
        """
        :param regex: regex pattern to match
        :param case_sensitive: should the match be case sensitive?
        :param match: should C{re.match} be used instead of C{re.search}?
        :param negate: should the match results be negated?
        """

        sf = object.__setattr__
        sf(self, "regex", regex)
        sf(self, "ismatch", match)
        sf(self, "negate", negate)
        flags = 0
        if not case_sensitive:
            flags = re.I
        sf(self, "flags", flags)
        try:
            compiled_re = re.compile(regex, flags)
        except re.error as e:
            raise ValueError("invalid regex: %r, %s" % (regex, e))
        if match:
            sf(self, "_matchfunc", compiled_re.match)
        else:
            sf(self, "_matchfunc", compiled_re.search)
        sf(self, "_hash", hash((self.regex, self.negate, self.flags, self.ismatch)))

    def match(self, value):
        if not isinstance(value, str):
            # Be too clever for our own good --marienz
            if value is None:
                value = ''
            else:
                value = str(value)
        return (self._matchfunc(value) is not None) != self.negate

    def __repr__(self):
        result = [self.__class__.__name__, repr(self.regex)]
        if self.negate:
            result.append('negated')
        if self.ismatch:
            result.append('match')
        else:
            result.append('search')
        result.append('@%#8x' % (id(self),))
        result = ' '.join(result)
        return f'<{result}>'

    def __str__(self):
        if self.ismatch:
            result = 'match '
        else:
            result = 'search '
        result += self.regex
        if self.negate:
            return f'not {result}'
        return result


class StrExactMatch(base, metaclass=generic_equality):
    """exact string comparison match"""

    __slots__ = __attr_comparison__ = ('_hash', 'exact', 'case_sensitive', 'negate')
    __inst_caching__ = True

    def __init__(self, exact, case_sensitive=True, negate=False):
        """
        :param exact: exact string to match
        :param case_sensitive: should the match be case sensitive?
        :param negate: should the match results be negated?
        """

        sf = object.__setattr__
        sf(self, "negate", negate)
        sf(self, "case_sensitive", case_sensitive)
        if not case_sensitive:
            sf(self, "exact", str(exact).lower())
        else:
            sf(self, "exact", str(exact))
        sf(self, "_hash", hash((self.exact, self.negate, self.case_sensitive)))

    def match(self, value):
        value = str(value)
        if self.case_sensitive:
            return (self.exact == value) != self.negate
        else:
            return (self.exact == value.lower()) != self.negate

    def intersect(self, other):
        s1, s2 = self.exact, other.exact
        if other.case_sensitive and not self.case_sensitive:
            s1 = s1.lower()
        elif self.case_sensitive and not other.case_sensitive:
            s2 = s2.lower()
        if s1 == s2 and self.negate == other.negate:
            if other.case_sensitive:
                return other
            return self
        return None

    def __repr__(self):
        if self.negate:
            string = '<%s %r negated @%#8x>'
        else:
            string = '<%s %r @%#8x>'
        return string % (self.__class__.__name__, self.exact, id(self))

    def __str__(self):
        if self.negate:
            return f'!= {self.exact}'
        return f'== {self.exact}'

    __hash__ = reflective_hash('_hash')


class StrGlobMatch(base, metaclass=hashed_base):
    """globbing matches; essentially startswith and endswith matches"""

    __slots__ = ('_hash', 'glob', 'prefix', 'negate', 'flags')
    __inst_caching__ = True

    def __init__(self, glob, case_sensitive=True, prefix=True, negate=False):
        """
        :param glob: string chunk that must be matched
        :param case_sensitive: should the match be case sensitive?
        :param prefix: should the glob be a prefix check for matching,
            or postfix matching
        :param negate: should the match results be negated?
        """

        sf = object.__setattr__
        sf(self, "negate", negate)
        if not case_sensitive:
            sf(self, "flags", re.I)
            sf(self, "glob", str(glob).lower())
        else:
            sf(self, "flags", 0)
            sf(self, "glob", str(glob))
        sf(self, "prefix", prefix)
        sf(self, "_hash", hash((self.glob, self.negate, self.flags, self.prefix)))

    def match(self, value):
        value = str(value)
        if self.flags == re.I:
            value = value.lower()
        if self.prefix:
            f = value.startswith
        else:
            f = value.endswith
        return f(self.glob) ^ self.negate

    def __repr__(self):
        if self.negate:
            string = '<%s %r case_sensitive=%r negated @%#8x>'
        else:
            string = '<%s %r case_sensitive=%r @%#8x>'
        if self.prefix:
            g = f'{self.glob}.*'
        else:
            g = f'.*{self.glob}'
        return string % (
            self.__class__.__name__, g,
            self.flags == re.I and True or False,
            id(self))

    def __str__(self):
        s = ''
        if self.negate:
            s = 'not '
        if self.prefix:
            return f'{s}{self.glob}*'
        return '{s}*{self.glob}'


class EqualityMatch(base, metaclass=generic_equality):

    __slots__ = ('negate', 'data')
    __attr_comparison__ = __slots__

    def __init__(self, data, negate=False):
        """
        :param data: data to base comparison against
        :param negate: should the results be negated?
        """

        sf = object.__setattr__
        sf(self, 'negate', negate)
        sf(self, "data", data)

    def __hash__(self):
        return hash((self.__class__, self.negate, self.data))

    def match(self, actual_val):
        return (self.data == actual_val) != self.negate

    def __repr__(self):
        return '<%s %r negate=%r @%#8x>' % (
            self.__class__.__name__, self.data, self.negate, id(self))

    def __str__(self):
        if self.negate:
            return f'EqualityMatch: !={self.data}'
        return f'EqualityMatch: ={self.data}'


class ContainmentMatch2(base, metaclass=hashed_base):
    """Used for an 'in' style operation.

    For example, 'x86' in ['x86', '~x86']. Note that negation of this *does*
    not result in a true NAND when all is on.

    Note that ContainmentMatch will be removed in favor of this class. When
    that occurs an alias will be left in place for compatibility.
    """

    __slots__ = ('_hash', 'vals', 'all', 'negate')
    __inst_caching__ = True

    def __init__(self, vals, match_all=False, negate=False):
        """
        :param vals: what values to look for during match
        :keyword all: must all vals be present, or just one for a match
            to succeed?
        :keyword negate: should the match results be negated?
        """

        sf = object.__setattr__
        sf(self, "all", bool(match_all))
        sf(self, "vals", frozenset((vals,) if isinstance(vals, str) else vals))
        sf(self, "negate", bool(negate))
        sf(self, "_hash", hash((self.all, self.negate, self.vals)))

    def match(self, val, _values_override=None):
        vals = _values_override
        if _values_override is None:
            vals = self.vals

        if isinstance(val, str):
            for fval in vals:
                if fval in val:
                    return not self.negate
            return self.negate

        # this can, and should be optimized to do len checks- iterate
        # over the smaller of the two see above about special casing
        # bits. need the same protection here, on the offchance (as
        # contents sets do), the __getitem__ is non standard.
        try:
            if self.all:
                return vals.issubset(val) != self.negate
            # if something intersects, then we return the inverse of negate-
            # if negate=False, something is found, result is True
            return vals.isdisjoint(val) == self.negate
        except TypeError:
            # isn't iterable, try the other way around.  rely on contains.
            if self.all:
                for k in vals:
                    if k not in val:
                        return self.negate
                return not self.negate
            for k in vals:
                if k in val:
                    return not self.negate

    def force_False(self, pkg, attr, val, _values_override=None):

        # "More than one statement on a single line"
        # pylint: disable-msg=C0321

        vals = _values_override
        if _values_override is None:
            vals = self.vals

        # XXX pretty much positive this isn't working.
        if isinstance(val, str) or not getattr(pkg, 'configurable', False):
            # unchangable
            return not self.match(val)

        if self.negate:
            if self.all:
                def filter(truths):
                    return False in truths
                def true(r, pvals):
                    return pkg.request_enable(attr, r)
                def false(r, pvals):
                    return pkg.request_disable(attr, r)

                truths = [x in val for x in vals]

                for x in boolean.iterative_quad_toggling(
                        pkg, None, list(vals), 0, len(vals), truths,
                        filter, desired_false=false, desired_true=true):
                    return True
            elif pkg.request_disable(attr, *vals):
                    return True
            return False

        if not self.all:
            return pkg.request_disable(attr, *vals)
        l = len(vals)
        def filter(truths): return truths.count(True) < l
        def true(r, pvals): return pkg.request_enable(attr, r)
        def false(r, pvals): return pkg.request_disable(attr, r)
        truths = [x in val for x in vals]
        for x in boolean.iterative_quad_toggling(
                pkg, None, list(vals), 0, l, truths, filter,
                desired_false=false, desired_true=true):
            return True
        return False

    def force_True(self, pkg, attr, val, _values_override=None):

        # "More than one statement on a single line"
        # pylint: disable-msg=C0321

        # XXX pretty much positive this isn't working.

        vals = _values_override
        if _values_override is None:
            vals = self.vals

        if isinstance(val, str) or not getattr(pkg, 'configurable', False):
            # unchangable
            return self.match(val)

        if not self.negate:
            if not self.all:
                def filter(truths):
                    return True in truths
                def true(r, pvals):
                    return pkg.request_enable(attr, r)
                def false(r, pvals):
                    return pkg.request_disable(attr, r)

                truths = [x in val for x in vals]

                for x in boolean.iterative_quad_toggling(
                        pkg, None, list(vals), 0, len(vals), truths,
                        filter, desired_false=false, desired_true=true):
                    return True
            else:
                if pkg.request_enable(attr, *vals):
                    return True
            return False

        # negation
        if not self.all:
            if pkg.request_disable(attr, *vals):
                return True
        else:
            def filter(truths): return True not in truths
            def true(r, pvals): return pkg.request_enable(attr, r)
            def false(r, pvals): return pkg.request_disable(attr, r)
            truths = [x in val for x in vals]
            for x in boolean.iterative_quad_toggling(
                    pkg, None, list(vals), 0, len(vals), truths, filter,
                    desired_false=false, desired_true=true):
                return True
        return False

    def __repr__(self):
        if self.negate:
            string = '<%s %r all=%s negated @%#8x>'
        else:
            string = '<%s %r all=%s @%#8x>'
        return string % (
            self.__class__.__name__, tuple(self.vals), self.all, id(self))

    def __str__(self):
        restricts_str = ', '.join(map(str, self.vals))
        negate = '!' if self.negate else ''
        return f'{negate}{restricts_str}'


class ContainmentMatch(ContainmentMatch2):
    """Used for an 'in' style operation.

    For example, 'x86' in ['x86', '~x86']. Note that negation of this *does*
    not result in a true NAND when all is on.

    Deprecated in favor of ContainmentMatch2.
    """

    __slots__ = ()
    __inst_caching__ = True

    def __init__(self, *args, **kwargs):
        # note that we're discarding any specialized __getitem__ on vals here.
        # this isn't optimal, and should be special cased for known
        # types (lists/tuples fex)
        vals = frozenset(args)
        match_all = kwargs.pop("all", False)
        ContainmentMatch2.__init__(self, vals, match_all=match_all, **kwargs)


class FlatteningRestriction(base, metaclass=generic_equality):
    """Flatten the values passed in and apply the nested restriction."""

    __slots__ = __attr_comparison__ = ('dont_iter', 'restriction', 'negate')
    __hash__ = object.__hash__

    def __init__(self, dont_iter, childrestriction, negate=False):
        """
        :type dont_iter: type or tuple of types
        :param dont_iter: type(s) not to flatten.
                          Passed to :obj:`snakeoil.sequences.iflatten_instance`.
        :type childrestriction: restriction
        :param childrestriction: restriction applied to the flattened list.
        """
        object.__setattr__(self, "negate", negate)
        object.__setattr__(self, "dont_iter", dont_iter)
        object.__setattr__(self, "restriction", childrestriction)

    def match(self, val):
        return self.restriction.match(
            iflatten_instance(val, self.dont_iter)) != self.negate

    def __str__(self):
        return (
            'flattening_restriction: '
            f'dont_iter = {self.dont_iter}, restriction = {self.restriction}'
        )

    def __repr__(self):
        return '<%s restriction=%r dont_iter=%r negate=%r @%#8x>' % (
            self.__class__.__name__,
            self.restriction, self.dont_iter, self.negate,
            id(self))


class FunctionRestriction(base, metaclass=generic_equality):
    """Convenience class for creating special restrictions."""

    __attr_comparison__ = __slots__ = ('func', 'negate')
    __hash__ = object.__hash__

    def __init__(self, func, negate=False):
        """
        C{func} is used as match function.

        It will usually be impossible for the backend to optimize this
        restriction. So even though you can implement an arbitrary
        restriction using this class you should only use it if it is
        very unlikely backend-specific optimizations will be possible.
        """
        object.__setattr__(self, 'negate', negate)
        object.__setattr__(self, 'func', func)

    def match(self, val):
        return self.func(val) != self.negate

    def __repr__(self):
        return '<%s func=%r negate=%r @%#8x>' % (
            self.__class__.__name__, self.func, self.negate, id(self))


class StrConversion(base, metaclass=generic_equality):
    """convert passed in data to a str object"""

    __hash__ = object.__hash__
    __attr_comparison__ = __slots__ = ('restrict',)

    def __init__(self, restrict):
        object.__setattr__(self, "restrict", restrict)

    def match(self, val):
        return self.restrict.match(str(val))


class UnicodeConversion(StrConversion):
    """convert passed in data to a unicode obj"""

    __slots__ = ()

    def match(self, val):
        return self.restrict.match(str(val))


class AnyMatch(restriction.AnyMatch):

    __slots__ = ()

    __hash__ = object.__hash__

    def __init__(self, childrestriction, negate=False):
        # Hack: skip calling base.__init__. Doing this would make
        # restriction.base.__init__ run twice.
        restriction.AnyMatch.__init__(
            self, childrestriction, restriction.value_type, negate=negate)

    def force_True(self, pkg, attr, val):
        return self.match(val)

    def force_False(self, pkg, attr, val):
        return not self.match(val)


# "Invalid name" (pylint uses the module const regexp, not the class regexp)
# pylint: disable-msg=C0103

AndRestriction = restriction.curry_node_type(boolean.AndRestriction,
                                             restriction.value_type)
OrRestriction = restriction.curry_node_type(boolean.OrRestriction,
                                            restriction.value_type)

AlwaysBool = restriction.curry_node_type(restriction.AlwaysBool,
                                         restriction.value_type)

AlwaysTrue = AlwaysBool(negate=True)
AlwaysFalse = AlwaysBool(negate=False)
