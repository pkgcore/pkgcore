# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
package wrapper class to override a packages attributes
"""


class MutatedPkg(object):
    __slots__ = ("_raw_pkg", "_overrides")

    def __init__(self, pkg, overrides):
        """
        @param pkg: L{pkgcore.package.metadata.package} to wrap
        @param overrides: is an attr -> instance mapping to substitute when the attr is requested
        """
        self._raw_pkg = pkg
        self._overrides = overrides

    def __getattr__(self, attr):
        if attr in self._overrides:
            return self._overrides[attr]
        return getattr(self._raw_pkg, attr)

    def __cmp__(self, other):
        if isinstance(other, self.__class__):
            return cmp(self._raw_pkg, other._raw_pkg)
        return cmp(self._raw_pkg, other)

    def __repr__(self):
        return '<%s pkg=%r overrides=%r @%#8x>' % (
            self.__class__.__name__, self._raw_pkg, tuple(self._overrides),
            id(self))

    def __str__(self):
        return '%s(%s, overrides=%s)' % \
            (self.__class__.__name__, self._raw_pkg, tuple(self._overrides))
