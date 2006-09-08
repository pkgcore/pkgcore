# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""Boolean combinations of restrictions.

This module provides classes that can be used to combine arbitrary
collections of restrictions in AND, NAND, OR, NOR, XOR, XNOR style
operations.
"""

__all__ = ("AndRestriction", "OrRestriction")

from itertools import islice
from pkgcore.restrictions import restriction


class base(restriction.base):

    """base template for boolean restrictions"""

    __slots__ = ("restrictions", "type")

    def __init__(self, *restrictions, **kwds):

        """
        @keyword node_type: type of restriction this accepts
            (L{package_type<pkgcore.restrictions.packages.package_type>} and
            L{value_type<pkgcore.restrictions.values.value_type>} being
            common types).  If set to C{None}, no instance limiting is done.
        @type  restrictions: node_type (if that is specified)
        @param restrictions: initial restrictions to add
        @keyword finalize: should this instance be made immutable immediately?
        @keyword negate: should the logic be negated?
        """

        if "node_type" in kwds:
            self.type = kwds["node_type"]
        finalize = kwds.pop("finalize", False)
        super(base, self).__init__(negate=kwds.get("negate", False))

        self.restrictions = []
        if restrictions:
            self.add_restriction(*restrictions)

        if finalize:
            self.restrictions = tuple(self.restrictions)

    def change_restrictions(self, *restrictions, **kwds):
        """
        return a new instance of self.__class__, using supplied restrictions

        """
        if self.__class__.type != self.type:
            kwds["node_type"] = self.type
        kwds["negate"] = self.negate
        return self.__class__(*restrictions, **kwds)

    def add_restriction(self, *new_restrictions):
        """
        add an more restriction(s)

        @param new_restrictions: if node_type is enforced,
            restrictions must be of that type.
        """

        if not new_restrictions:
            raise TypeError("need at least one restriction handed in")
        if hasattr(self, "type"):
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

        self.restrictions.extend(new_restrictions)

    def finalize(self):
        """
        finalize the restriction instance, disallowing adding restrictions.
        """
        self.restrictions = tuple(self.restrictions)

    def __repr__(self):
        return '<%s restrictions=%r @%#8x>' % (
            self.__class__.__name__, self.restrictions, id(self))

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
        return self.cnf_solutions(*a, **kwds)

    def iter_dnf_solutions(self, *a, **kwds):
        """iterate over the dnf solution"""
        return self.dnf_solutions(*a, **kwds)

    def __getitem__(self, key):
        return self.restrictions[key]


# this beast, handles N^2 permutations.  convert to stack based.
def iterative_quad_toggling(pkg, pvals, restrictions, starting, end, truths,
                            filter, desired_false=None, desired_true=None,
                            kill_switch=None):
    if desired_false is None:
        desired_false = lambda r, a:r.force_False(*a)
    if desired_true is None:
        desired_true = lambda r, a:r.force_True(*a)

#    import pdb;pdb.set_trace()
    reset = True
    if starting == 0:
        if filter(truths):
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
                if filter(t):
                    yield True
                for i in iterative_quad_toggling(
                    pkg, pvals, restrictions, index + 1, end, t, filter,
                    desired_false=desired_false, desired_true=desired_true,
                    kill_switch=kill_switch):
#                    import pdb;pdb.set_trace()
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
                if filter(t):
                    yield True
                for x in iterative_quad_toggling(
                    pkg, pvals, restrictions, index + 1, end, t, filter,
                    desired_false=desired_false, desired_true=desired_true):
#                    import pdb;pdb.set_trace()
                    yield True
                reset = True
            elif index == end:
                if filter(truths):
#                    import pdb;pdb.set_trace()
                    yield True
            else:
                if kill_switch is not None and kill_switch(truths, index):
                    return

        if reset:
            pkg.rollback(entry)


class AndRestriction(base):
    """Boolean AND grouping of restrictions.  negation is a NAND"""
    __slots__ = ()

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
        def filter(truths):
            return False in truths

        for i in iterative_quad_toggling(pkg, pvals, self.restrictions, 0,
                                         len(self.restrictions), truths,
                                         filter):
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
        def filter(truths):
            return False in truths
        for i in iterative_quad_toggling(pkg, pvals, self.restrictions, 0,
                                         len(self.restrictions), truths,
                                         filter):
            return True
        return False

    def iter_dnf_solutions(self, full_solution_expansion=False):
        """
        generater yielding DNF (disjunctive normalized form) of this instance.

        @param full_solution_expansion: controls whether to expand everything
            (break apart atoms for example); this isn't likely what you want
        """
        if self.negate:
#           raise NotImplementedError("negation for dnf_solutions on "
#                 "AndRestriction isn't implemented yet")
            # hack- this is an experiment
            for r in OrRestriction(
                type=self.type, strict=False,
                *[restriction.Negate(x)
                  for x in self.restrictions]).iter_dnf_solutions():
                yield r
            return
        if not self.restrictions:
            yield []
            return
        hardreqs = []
        optionals = []
        for x in self.restrictions:
            if isinstance(x, base):
                s2 = x.dnf_solutions(
                    full_solution_expansion=full_solution_expansion)
                assert s2
                if len(s2) == 1:
                    hardreqs.extend(s2[0])
                else:
                    optionals.append(s2)
            else:
                hardreqs.append(x)
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
        """
        list form of L{iter_dnf_solutions}, see iter_dnf_solutions for args
        """
        return list(self.iter_dnf_solutions(*args, **kwds))

    def cnf_solutions(self, full_solution_expansion=False):

        """
        returns solutions in CNF (conjunctive normalized form) of this instance

        @param full_solution_expansion: controls whether to expand everything
            (break apart atoms for example); this isn't likely what you want
        """

        if self.negate:
            raise NotImplementedError("negation for solutions on "
                                      "AndRestriction isn't implemented yet")
        andreqs = []
        for x in self.restrictions:
            if isinstance(x, base):
                andreqs.extend(x.cnf_solutions(
                        full_solution_expansion=full_solution_expansion))
            else:
                andreqs.append([x])
        return andreqs

    def __str__(self):
        if self.negate:
            return "not ( %s )" % " && ".join(str(x) for x in self.restrictions)
        return "( %s )" % " && ".join(str(x) for x in self.restrictions)


class OrRestriction(base):
    """Boolean OR grouping of restrictions."""
    __slots__ = ()

    def match(self, vals):
        for rest in self.restrictions:
            if rest.match(vals):
                return not self.negate
        return self.negate

    def cnf_solutions(self, full_solution_expansion=False):
        """
        returns alist in CNF (conjunctive normalized form) for of this instance

        @param full_solution_expansion: controls whether to expand everything
            (break apart atoms for example); this isn't likely what you want
        """
        if self.negate:
            raise NotImplementedError(
                "OrRestriction.solutions doesn't yet support self.negate")

        if not self.restrictions:
            return []

        def f(arg, *others):
            if others:
                for node2 in f(*others):
                    yield arg + node2
            else:
                yield [arg]


        dcnf = []
        cnf = []
        for x in self.restrictions:
            if isinstance(x, base):
                s2 = x.dnf_solutions(
                    full_solution_expansion=full_solution_expansion)
                if len(s2) == 1:
                    cnf.extend(s2)
                else:
                    for y in s2:
                        if len(y) == 1:
                            dcnf.append(y[0])
                        else:
                            cnf.append(y)
            else:
                dcnf.append(x)

        # combinatorial explosion. if it's got cnf, we peel off one of
        # each and smash append to the dcnf.
        dcnf = [dcnf]
        for andreq in cnf:
            dcnf = list([x] + y for x in andreq for y in dcnf)
        return dcnf


    def iter_dnf_solutions(self, full_solution_expansion=False):
        """
        returns a list in DNF (disjunctive normalized form) for of this instance

        @param full_solution_expansion: controls whether to expand everything
            (break apart atoms for example); this isn't likely what you want
        """
        if self.negate:
            # hack- this is an experiment
            for x in AndRestriction(
                type=self.type, strict=False,
                *[restriction.Negate(x)
                  for x in self.restrictions]).iter_dnf_solutions():
                yield x
        if not self.restrictions:
            yield []
            return
        for x in self.restrictions:
            if isinstance(x, base):
                for y in x.iter_dnf_solutions(
                    full_solution_expansion=full_solution_expansion):
                    yield y
            else:
                yield [x]

    def dnf_solutions(self, *args, **kwds):
        """
        see dnf_solutions, iterates yielding DNF solutions
        """
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
        def filter(truths):
            return True in truths
        for i in iterative_quad_toggling(pkg, pvals, self.restrictions, 0,
                                         len(self.restrictions), truths,
                                         filter):
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
        def filter(truths):
            return True in truths
        for i in iterative_quad_toggling(pkg, pvals, self.restrictions, 0,
                                         len(self.restrictions), truths,
                                         filter):
            yield True


    def __str__(self):
        if self.negate:
            return "not ( %s )" % " || ".join(str(x) for x in self.restrictions)
        return "( %s )" % " || ".join(str(x) for x in self.restrictions)
