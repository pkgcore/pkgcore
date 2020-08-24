"""
restriction related utilities
"""

from snakeoil.sequences import iflatten_func

from . import boolean, packages, restriction


def _is_package_instance(inst):
    return (getattr(inst, "type", None) == restriction.package_type and not
            isinstance(inst, boolean.base))


def collect_package_restrictions(restrict, attrs=None, invert=False):
    """Collect PackageRestriction instances inside a restriction.

    :param restrict: package instance to scan
    :param attrs: None (return all package restrictions), or a sequence of
        specific attrs the package restriction must work against.
    """
    if not isinstance(restrict, (list, tuple)):
        restrict = [restrict]
    for r in restrict:
        if not isinstance(r, restriction.base):
            raise TypeError(
                'restrict must be of a restriction.base, '
                f'not {r.__class__.__class__}: {r!r}'
            )
    i = iflatten_func(restrict, _is_package_instance)
    if attrs is None:
        return i
    attrs = frozenset(attrs)
    return (
        r for r in i
        if invert == attrs.isdisjoint(getattr(r, 'attrs', ()))
    )
