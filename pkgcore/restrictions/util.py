# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
restriction related utilities
"""

from pkgcore.restrictions import packages, boolean, restriction
from snakeoil.lists import iflatten_func

def _is_package_instance(inst):
    return (getattr(inst, "type", None) == packages.package_type
            and not isinstance(inst, boolean.base))

def collect_package_restrictions(restrict, attrs=None):
    """Collect PackageRestriction instances inside a restriction.

    @param restrict: package instance to scan
    @param attrs: None (return all package restrictions), or a sequence of
        specific attrs the package restriction must work against.
    """
    if not isinstance(restrict, (list, tuple)):
        restrict = [restrict]
    for r in restrict:
        if not isinstance(r, restriction.base):
            raise TypeError(
                "restrict must be of a restriction.base, not %s: %r" % (
                    r.__class__.__name__, r))
    if attrs is None:
        for r in iflatten_func(restrict, _is_package_instance):
            yield r
    else:
        if isinstance(attrs, (list, tuple)):
            attrs = frozenset(attrs)
        for r in iflatten_func(restrict, _is_package_instance):
            if getattr(r, "attr", None) in attrs:
                yield r
