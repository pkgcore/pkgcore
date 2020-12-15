"""Boolean combinations of restrictions.

This module provides classes that can be used to combine arbitrary
collections of restrictions in AND, NAND, OR, NOR, XOR, XNOR style
operations.
"""

__all__ = ("AndRestriction", "OrRestriction")

from itertools import islice

from snakeoil.klass import cached_hash, generic_equality

from . import restriction


class base(restriction.base, metaclass=generic_equality):
    """base template for boolean restrictions"""
    __attr_comparison__ = ('negate', 'type', 'restrictions')
    __slots__ = ('restrictions', 'type', 'negate', '_hash')

    _evaluate_collapsible = False
    _evaluate_wipe_empty = True

    @cached_hash
    def __hash__(self):
        if not isinstance(self.restrictions, tuple):
            raise TypeError(f"{self!r} isn't finalized")
        return hash(tuple(getattr(self, x) for x in self.__attr_comparison__))

    def __init__(self, *restrictions, **kwds):
        """
        :keyword node_type: type of restriction this accepts
            (:obj:`pkgcore.restrictions.restriction.package_type` and
            :obj:`pkgcore.restrictions.restriction.value_type` being
            common types).  If set to C{None}, no instance limiting is done.
        :type restrictions: node_type (if that is specified)
        :param restrictions: initial restrictions to add
        :keyword finalize: should this instance be made immutable immediately?
            defaults to True
        :keyword negate: should the logic be negated?
        """

        sf = object.__setattr__

        node_type = kwds.pop("node_type", None)

        sf(self, "type", node_type)
        sf(self, "negate", kwds.pop("negate", False))

        if node_type is not None:
            try:
                for r in restrictions:
                    if r.type is not None and r.type != node_type:
                        raise TypeError(
                            "instance '%s' is restriction type '%s', "
                            "must be '%s'" % (r, r.type, node_type))
            except AttributeError:
                raise TypeError(
                    "type '%s' instance '%s' has no restriction type, "
                    "'%s' required" % (
                        r.__class__, r, node_type))

        if kwds.pop("finalize", True):
            if not isinstance(restrictions, tuple):
                sf(self, "restrictions", tuple(restrictions))
            else:
                sf(self, "restrictions", restrictions)
        else:
            sf(self, "restrictions", list(restrictions))

        if kwds:
            kwds.pop("disable_inst_caching", None)
            if kwds:
                raise TypeError(
                    "unknown keywords to %s: %s" %
                    (self.__class__, kwds))

    def change_restrictions(self, *restrictions, **kwds):
        """return a new instance of self.__class__, using supplied restrictions"""
        if self.type is not None:
            if self.__class__.type not in restriction.valid_types or \
                    self.__class__.type != self.type:
                kwds["node_type"] = self.type
        kwds.setdefault("negate", self.negate)
        return self.__class__(*restrictions, **kwds)

    def remove_restriction(self, restriction_types=(), *restrictions):
        """return a new instance of self.__class__, dropping supplied restrictions or types"""
        new_restrictions = tuple(
            r for r in self.restrictions if
            not isinstance(r, tuple(restriction_types))
            and r not in restrictions)
        if new_restrictions != self.restrictions:
            return self.change_restrictions(*new_restrictions)
        return self

    def add_restriction(self, *new_restrictions):
        """add more restriction(s)

        :param new_restrictions: if node_type is enforced,
            restrictions must be of that type.
        """
        if not new_restrictions:
            raise TypeError("need at least one restriction handed in")
        if self.type is not None:
            try:
                for r in new_restrictions:
                    if r.type is not None and r.type != self.type:
                        raise TypeError(
                            "instance '%s' is restriction type '%s', "
                            "must be '%s'" % (r, r.type, self.type))
            except AttributeError:
                raise TypeError(
                    "type '%s' instance '%s' has no restriction type, "
                    "'%s' required" % (
                        r.__class__, r, getattr(self, "type", "unset")))

        try:
            self.restrictions.extend(new_restrictions)
        except AttributeError:
            raise TypeError("%r is finalized" % self)

    def finalize(self):
        """finalize the restriction instance, disallowing adding restrictions."""
        object.__setattr__(self, "restrictions", tuple(self.restrictions))

    def __repr__(self):
        return '<%s negate=%r type=%r finalized=%r restrictions=%r @%#8x>' % (
            self.__class__.__name__, self.negate, getattr(self, 'type', None),
            isinstance(self.restrictions, tuple), self.restrictions,
            id(self))

    def __len__(self):
        return len(self.restrictions)

    def __iter__(self):
        return iter(self.restrictions)

    def match(self, action, *vals):
        raise NotImplementedError

    force_False, force_True = match, match

    def dnf_solutions(self, full_solution_expansion=False):
        raise NotImplementedError()

    cnf_solutions = dnf_solutions

    def iter_cnf_solutions(self, *a, **kwds):
        """iterate over the cnf solution"""
        return iter(self.cnf_solutions(*a, **kwds))

    def iter_dnf_solutions(self, *a, **kwds):
        """iterate over the dnf solution"""
        return iter(self.dnf_solutions(*a, **kwds))

    def __getitem__(self, key):
        return self.restrictions[key]

    def evaluate_conditionals(self, parent_cls, parent_seq, enabled,
                              tristate_locked=None, force_collapse=False):
        l = []
        for restrict in self:
            f = getattr(restrict, 'evaluate_conditionals', None)
            if f is None:
                l.append(restrict)
            else:
                f(self.__class__, l, enabled, tristate_locked)

        if not self._evaluate_wipe_empty or l:
            if force_collapse or (
                    (issubclass(parent_cls, self.__class__) and self._evaluate_collapsible) or
                    len(l) <= 1):
                parent_seq.extend(l)
            else:
                parent_seq.append(self.__class__(*l))


# this beast, handles N^2 permutations.  convert to stack based.
def iterative_quad_toggling(pkg, pvals, restrictions, starting, end, truths,
                            filter_func, desired_false=None, desired_true=None,
                            kill_switch=None):
    if desired_false is None:
        desired_false = lambda r, a: r.force_False(*a)
    if desired_true is None:
        desired_true = lambda r, a: r.force_True(*a)

    reset = True
    if starting == 0:
        if filter_func(truths):
            yield True
    for index, rest in islice(enumerate(restrictions), starting, end):
        if reset:
            entry = pkg.changes_count()
        reset = False
        if truths[index]:
            if desired_false(rest, pvals):
                reset = True
                t = truths[:]
                t[index] = False
                if filter_func(t):
                    yield True
                for i in iterative_quad_toggling(
                        pkg, pvals, restrictions, index + 1, end, t, filter_func,
                        desired_false=desired_false, desired_true=desired_true,
                        kill_switch=kill_switch):
                    yield True
                reset = True
            else:
                if kill_switch is not None and kill_switch(truths, index):
                    return
        else:
            if desired_true(rest, pvals):
                reset = True
                t = truths[:]
                t[index] = True
                if filter_func(t):
                    yield True
                for x in iterative_quad_toggling(
                        pkg, pvals, restrictions, index + 1, end, t, filter_func,
                        desired_false=desired_false, desired_true=desired_true):
                    yield True
                reset = True
            elif index == end:
                if filter_func(truths):
                    yield True
            else:
                if kill_switch is not None and kill_switch(truths, index):
                    return

        if reset:
            pkg.rollback(entry)


class AndRestriction(base):
    """Boolean AND grouping of restrictions.  negation is a NAND"""
    __slots__ = ()

    _evaluate_collapsible = True

    def match(self, vals):
        for rest in self.restrictions:
            if not rest.match(vals):
                return self.negate
        return not self.negate

    def force_True(self, pkg, *vals):
        pvals = [pkg]
        pvals.extend(vals)
        entry_point = pkg.changes_count()
        # get the simple one out of the way first.
        if not self.negate:
            for r in self.restrictions:
                if not r.force_True(*pvals):
                    pkg.rollback(entry_point)
                    return False
            return True

        # <insert page long curse here>, NAND logic,
        # len(restrictions)**2 potential solutions.
        # 0|0 == 0, 0|1 == 1|0 == 0|0 == 1.
        # XXX this is quadratic. patches welcome to dodge the
        # requirement to push through all potential truths.
        truths = [r.match(*pvals) for r in self.restrictions]

        def filter_func(truths):
            return False in truths

        for i in iterative_quad_toggling(pkg, pvals, self.restrictions, 0,
                                         len(self.restrictions), truths,
                                         filter_func):
            return True
        return False

    def force_False(self, pkg, *vals):
        pvals = [pkg]
        pvals.extend(vals)
        entry_point = pkg.changes_count()
        # get the simple one out of the way first.
        if self.negate:
            for r in self.restrictions:
                if not r.force_True(*pvals):
                    pkg.rollback(entry_point)
                    return False
            return True

        # <insert page long curse here>, NAND logic,
        # (len(restrictions)^2)-1 potential solutions.
        # 1|1 == 0, 0|1 == 1|0 == 0|0 == 1.
        # XXX this is quadratic. patches welcome to dodge the
        # requirement to push through all potential truths.
        truths = [r.match(*pvals) for r in self.restrictions]

        def filter_func(truths):
            return False in truths
        for i in iterative_quad_toggling(pkg, pvals, self.restrictions, 0,
                                         len(self.restrictions), truths,
                                         filter_func):
            return True
        return False

    def iter_dnf_solutions(self, full_solution_expansion=False):
        """generater yielding DNF (disjunctive normalized form) of this instance.

        :param full_solution_expansion: controls whether to expand everything
            (break apart atoms for example); this isn't likely what you want
        """
        if self.negate:
#           raise NotImplementedError("negation for dnf_solutions on "
#                 "AndRestriction isn't implemented yet")
            # hack- this is an experiment
            for r in OrRestriction(
                    node_type=self.type, *[restriction.Negate(x)
                    for x in self.restrictions]).iter_dnf_solutions():
                yield r
            return
        if not self.restrictions:
            yield []
            return
        hardreqs = []
        optionals = []
        for x in self.restrictions:
            method = getattr(x, 'dnf_solutions', None)
            if method is None:
                hardreqs.append(x)
            else:
                s2 = method(full_solution_expansion)
                assert s2
                if len(s2) == 1:
                    hardreqs.extend(s2[0])
                else:
                    optionals.append(s2)

        def f(arg, *others):
            if others:
                for node in arg:
                    for node2 in f(*others):
                        yield node + node2
            else:
                for node in arg:
                    yield node

        for solution in f([hardreqs], *optionals):
            assert isinstance(solution, (tuple, list))
            yield solution

    def dnf_solutions(self, *args, **kwds):
        """list form of :obj:`iter_dnf_solutions`, see iter_dnf_solutions for args"""
        return list(self.iter_dnf_solutions(*args, **kwds))

    def iter_cnf_solutions(self, full_solution_expansion=False):
        """returns solutions in CNF (conjunctive normalized form) of this instance

        :param full_solution_expansion: controls whether to expand everything
            (break apart atoms for example); this isn't likely what you want
        """

        if self.negate:
            raise NotImplementedError("negation for solutions on "
                                      "AndRestriction isn't implemented yet")
        for x in self.restrictions:
            method = getattr(x, 'iter_cnf_solutions', None)
            if method is None:
                yield [x]
            else:
                for y in method(full_solution_expansion):
                    yield y

    def cnf_solutions(self, full_solution_expansion=False):
        """returns solutions in CNF (conjunctive normalized form) of this instance

        :param full_solution_expansion: controls whether to expand everything
            (break apart atoms for example); this isn't likely what you want
        """

        if self.negate:
            raise NotImplementedError("negation for solutions on "
                                      "AndRestriction isn't implemented yet")
        andreqs = []
        for x in self.restrictions:
            method = getattr(x, 'iter_cnf_solutions', None)
            if method is None:
                andreqs.append([x])
            else:
                andreqs.extend(method(full_solution_expansion))
        return andreqs

    def __str__(self):
        restricts_str = " && ".join(map(str, self.restrictions))
        negate = 'not ' if self.negate else ''
        return f'{negate}( {restricts_str} )'


class OrRestriction(base):
    """Boolean OR grouping of restrictions."""
    __slots__ = ()

    _evaluate_collapsible = True

    def match(self, vals):
        for rest in self.restrictions:
            if rest.match(vals):
                return not self.negate
        return self.negate

    def cnf_solutions(self, full_solution_expansion=False):
        """Returns a list in CNF (conjunctive normalized form) of this instance.

        :param full_solution_expansion: controls whether to expand everything
            (break apart atoms for example); this isn't likely what you want
        """
        if self.negate:
            raise NotImplementedError(
                "OrRestriction.solutions doesn't yet support self.negate")

        if not self.restrictions:
            return []

        dcnf = []
        cnf = []
        for x in self.restrictions:
            method = getattr(x, 'dnf_solutions', None)
            if method is None:
                dcnf.append(x)
            else:
                s2 = method(full_solution_expansion)
                if len(s2) == 1:
                    cnf.extend(s2)
                else:
                    for y in s2:
                        if len(y) == 1:
                            dcnf.append(y[0])
                        else:
                            cnf.append(y)

        # combinatorial explosion. if it's got cnf, we peel off one of
        # each and smash append to the dcnf.
        dcnf = [dcnf]
        for andreq in cnf:
            dcnf = list(y + [x] for x in andreq for y in dcnf)
        return dcnf

    def iter_dnf_solutions(self, full_solution_expansion=False):
        """Returns a list in DNF (disjunctive normalized form) of this instance.

        :param full_solution_expansion: controls whether to expand everything
            (break apart atoms for example); this isn't likely what you want
        """
        if self.negate:
            # hack- this is an experiment
            for x in AndRestriction(
                node_type=self.type,
                *[restriction.Negate(x)
                  for x in self.restrictions]).iter_dnf_solutions():
                yield x
        if not self.restrictions:
            yield []
            return
        for x in self.restrictions:
            method = getattr(x, 'iter_dnf_solutions', None)
            if method is None:
                yield [x]
            else:
                for y in method(full_solution_expansion):
                    yield y

    def dnf_solutions(self, *args, **kwds):
        """see dnf_solutions, iterates yielding DNF solutions"""
        return list(self.iter_dnf_solutions(*args, **kwds))

    def force_True(self, pkg, *vals):
        pvals = [pkg]
        pvals.extend(vals)
        entry_point = pkg.changes_count()
        # get the simple one out of the way first.
        if self.negate:
            for r in self.restrictions:
                if not r.force_False(*pvals):
                    pkg.rollback(entry_point)
                    return False
            return True

        # <insert page long curse here>, OR logic,
        # len(restrictions)**2-1 potential solutions.
        # 0|0 == 0, 0|1 == 1|0 == 1|1 == 1.
        # XXX this is quadratic. patches welcome to dodge the
        # requirement to push through all potential truths.
        truths = [r.match(*pvals) for r in self.restrictions]

        def filter_func(truths):
            return True in truths
        for i in iterative_quad_toggling(pkg, pvals, self.restrictions, 0,
                                         len(self.restrictions), truths,
                                         filter_func):
            return True
        return False

    def force_False(self, pkg, *vals):
        pvals = [pkg]
        pvals.extend(vals)
        entry_point = pkg.changes_count()
        # get the simple one out of the way first.
        if not self.negate:
            for r in self.restrictions:
                if not r.force_False(*pvals):
                    pkg.rollback(entry_point)
                    return
            yield True
            return

        # <insert page long curse here>, OR logic,
        # (len(restrictions)**2)-1 potential solutions.
        # 0|0 == 0, 0|1 == 1|0 == 1|1 == 1.
        # XXX this is quadratic. patches welcome to dodge the
        # requirement to push through all potential truths.
        truths = [r.match(*pvals) for r in self.restrictions]

        def filter_func(truths):
            return True in truths
        for i in iterative_quad_toggling(pkg, pvals, self.restrictions, 0,
                                         len(self.restrictions), truths,
                                         filter_func):
            yield True

    def __str__(self):
        restricts_str = " || ".join(map(str, self.restrictions))
        negate = 'not ' if self.negate else ''
        return f'{negate}( {restricts_str} )'


class JustOneRestriction(base):
    """Exactly one must match, or there must be no restrictions"""

    __slots__ = ()

    _evaluate_collapsable = True
    _evaluate_wipe_empty = False

    def match(self, vals):
        if not self.restrictions:
            return not self.negate

        armed = False
        for node in self.restrictions:
            if node.match(vals):
                # two matches found?
                if armed:
                    return self.negate
                armed = True
        if armed:
            return not self.negate
        return self.negate

    def __str__(self):
        restricts_str = " ".join(map(str, self.restrictions))
        negate = 'not ' if self.negate else ''
        return f'{negate}exactly-one-of ( {restricts_str} )'


class AtMostOneOfRestriction(base):
    """Either none, or exactly one match must occur."""

    __slots__ = ()

    _evaluate_collapsable = True
    _evaluate_wipe_empty = False

    def match(self, vals):
        armed = False
        for restrict in self.restrictions:
            if not restrict.match(vals):
                continue
            if armed:
                return self.negate
            armed = True
        return not self.negate

    def __str__(self):
        restricts_str = " ".join(map(str, self.restrictions))
        negate = 'not ' if self.negate else ''
        return f'{negate}at-most-one-of ( {restricts_str} )'
