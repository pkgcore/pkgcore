# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
restriction related utilities
"""

from pkgcore.util.lists import iflatten_func
from pkgcore.util.containers import InvertedContains
from pkgcore.restrictions import packages, boolean

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
    if attrs is None:
        for r in iflatten_func(restrict, _is_package_instance):
            yield r
    else:
        if isinstance(attrs, (list, tuple)):
            attrs = frozenset(attrs)
        for r in iflatten_func(restrict, _is_package_instance):
            if getattr(r, "attr", None) in attrs:
                yield r
