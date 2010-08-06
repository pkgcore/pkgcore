# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
base package class; instances should derive from this.

Right now, doesn't provide much, need to change that down the line
"""

__all__ = ("base", "wrapper", "dynamic_getattr_dict")

from snakeoil.compatibility import cmp
from snakeoil import klass

class base(object):

    built = False
    configurable = False

    __slots__ = ("__weakref__",)
    _get_attr = {}

    def __setattr__(self, attr, value):
        raise AttributeError(self, attr)

    def __delattr__(self, attr):
        raise AttributeError(self, attr)

    @property
    def versioned_atom(self):
        raise NotImplementedError(self, "versioned_atom")

    @property
    def unversioned_atom(self):
        raise NotImplementedError(self, "versioned_atom")


class wrapper(base):

    __slots__ = ("_raw_pkg",)

    klass.inject_richcmp_methods_from_cmp(locals())

    def __init__(self, raw_pkg):
        object.__setattr__(self, "_raw_pkg", raw_pkg)

    def __cmp__(self, other):
        if isinstance(other, wrapper):
            return cmp(self._raw_pkg, other._raw_pkg)
        return cmp(self._raw_pkg, other)

    def __eq__(self, other):
        if isinstance(other, wrapper):
            return cmp(self._raw_pkg, other._raw_pkg) == 0
        return cmp(self._raw_pkg, other) == 0

    def __ne__(self, other):
        return not self == other

    __getattr__ = klass.GetAttrProxy("_raw_pkg")

    built = klass.alias_attr("_raw_pkg.built")
    versioned_atom = klass.alias_attr("_raw_pkg.versioned_atom")
    unversioned_atom = klass.alias_attr("_raw_pkg.unversioned_atom")

    def __hash__(self):
        return hash(self._raw_pkg)

def dynamic_getattr_dict(self, attr):
    try:
        val = self._get_attr[attr](self)
        object.__setattr__(self, attr, val)
        return val
    except KeyError:
        raise AttributeError(self, attr)

