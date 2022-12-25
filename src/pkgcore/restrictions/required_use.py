from typing import Iterator, Protocol

from snakeoil.constraints import Constraint, Problem
from . import restriction, boolean, packages, values


class _use_constraint(Protocol):
    def __call__(self, on: frozenset[str]) -> bool:
        raise NotImplementedError("Constraint", "__call__")


def __use_flags_state_any(negate: bool, vals: frozenset[str]) -> _use_constraint:
    def check(on: frozenset[str]):
        return vals.isdisjoint(on) == negate

    return check


def __condition(
    negate: bool, vals: frozenset[str], *children: _use_constraint
) -> _use_constraint:
    def check(on: frozenset[str]):
        return vals.issubset(on) == negate or all(c(on) for c in children)

    return check


def __or_constraint(negate: bool, *children: _use_constraint) -> _use_constraint:
    def check(on: frozenset[str]):
        return any(c(on) for c in children) != negate

    return check


def __and_constraint(negate: bool, *children: _use_constraint) -> _use_constraint:
    def check(on: frozenset[str]):
        return all(c(on) for c in children) != negate

    return check


def __just_one_constraint(negate: bool, *children: _use_constraint) -> _use_constraint:
    def check(on: frozenset[str]):
        return (1 == sum(c(on) for c in children)) != negate

    return check


def __at_most_one_constraint(
    negate: bool, *children: _use_constraint
) -> _use_constraint:
    def check(on: frozenset[str]):
        return (1 >= sum(c(on) for c in children)) != negate

    return check


def __to_single_constraint(restrict) -> tuple[_use_constraint, frozenset[str]]:
    if isinstance(restrict, values.ContainmentMatch):
        assert not restrict.all
        return __use_flags_state_any(
            restrict.negate, frozenset(restrict.vals)
        ), frozenset(restrict.vals)
    elif isinstance(restrict, packages.Conditional):
        assert isinstance(x := restrict.restriction, values.ContainmentMatch)
        children, variables = zip(
            *(__to_single_constraint(c) for c in restrict.payload)
        )
        return __condition(x.negate, frozenset(x.vals), *children), frozenset(
            x.vals
        ).union(*variables)
    elif isinstance(restrict, boolean.OrRestriction):
        children, variables = zip(
            *(__to_single_constraint(c) for c in restrict.restrictions)
        )
        return __or_constraint(restrict.negate, *children), frozenset().union(
            *variables
        )
    elif isinstance(restrict, boolean.AndRestriction):
        children, variables = zip(
            *(__to_single_constraint(c) for c in restrict.restrictions)
        )
        return __and_constraint(restrict.negate, *children), frozenset().union(
            *variables
        )
    elif isinstance(restrict, boolean.JustOneRestriction):
        children, variables = zip(
            *(__to_single_constraint(c) for c in restrict.restrictions)
        )
        return __just_one_constraint(restrict.negate, *children), frozenset().union(
            *variables
        )
    elif isinstance(restrict, boolean.AtMostOneOfRestriction):
        children, variables = zip(
            *(__to_single_constraint(c) for c in restrict.restrictions)
        )
        return __at_most_one_constraint(restrict.negate, *children), frozenset().union(
            *variables
        )
    else:
        raise NotImplementedError("build_constraint", type(restrict))


def __to_multiple_constraint(
    restrict,
) -> Iterator[tuple[_use_constraint, frozenset[str]]]:
    if isinstance(restrict, packages.Conditional):
        assert isinstance(x := restrict.restriction, values.ContainmentMatch)
        for rule in restrict.payload:
            for func, variables in __to_multiple_constraint(rule):
                yield __condition(x.negate, frozenset(x.vals), func), frozenset(
                    x.vals
                ).union(variables)
    elif isinstance(restrict, boolean.AndRestriction):
        assert not restrict.negate
        for rule in restrict.restrictions:
            yield from __to_multiple_constraint(rule)
    else:
        yield __to_single_constraint(restrict)


def __wrapper(constraint_func: _use_constraint) -> Constraint:
    def check(**kwargs):
        return constraint_func(frozenset(k for k, v in kwargs.items() if v))

    return check


def find_constraint_satisfaction(
    restricts: restriction.base,
    iuse: set[str],
    force_true=(),
    force_false=(),
    prefer_true=(),
) -> Iterator[dict[str, bool]]:
    """Return iterator for use flags combination satisfying REQUIRED_USE

    :param restricts: Parsed restricts of REQUIRED_USE
    :param iuse: Known IUSE for the restricts. Any USE flag encountered
        not in this set, will be forced to a False value.
    :param force_true: USE flags which will be force to only True value.
    :param force_false: USE flags which will be force to only False value.
    :param prefer_true: USE flags which will have a preference to True value.
        All other flags, which aren't forced, will have a preference to False.
    :return: Iterator returning satisfying use flags combination, of USE flag
        and it's state.
    """
    problem = Problem()

    prefer_false = iuse.difference(force_true, force_false, prefer_true)
    problem.add_variable((True, False), *prefer_false)
    problem.add_variable(
        (False, True),
        *iuse.intersection(prefer_true).difference(force_false, force_true),
    )
    problem.add_variable((False,), *iuse.intersection(force_false))
    problem.add_variable((True,), *iuse.intersection(force_true))

    for rule in restricts:
        for constraint_func, variables in __to_multiple_constraint(rule):
            if missing_vars := variables - problem.variables.keys():
                problem.add_variable((False,), *missing_vars)
            problem.add_constraint(__wrapper(constraint_func), variables)
    return iter(problem)
