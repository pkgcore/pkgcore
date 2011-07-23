# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
base package class; instances should derive from this.

Right now, doesn't provide much, need to change that down the line
"""

__all__ = ("base", "wrapper", "dynamic_getattr_dict")

from snakeoil.compatibility import cmp
from snakeoil import klass

from pkgcore.operations import format

class base(object):

    built = False
    configurable = False
    _operations = format.operations

    __metaclass__ = klass.immutable_instance

    __slots__ = ("__weakref__",)
    _get_attr = {}

    @property
    def versioned_atom(self):
        raise NotImplementedError(self, "versioned_atom")

    @property
    def unversioned_atom(self):
        raise NotImplementedError(self, "unversioned_atom")

    def operations(self, domain, **kwds):
        return self._operations(domain, self, **kwds)

    @property
    def repo_id(self):
        """Initially set to None. will be overriden later
        when appropriate"""
        return None


class wrapper(base):

    __slots__ = ("_raw_pkg",)

    klass.inject_richcmp_methods_from_cmp(locals())

    def operations(self, domain, **kwds):
        return self._raw_pkg._operations(domain, self, **kwds)

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
