"""
package wrapper class to override a packages attributes
"""

__all__ = ("MutatedPkg",)

from .base import wrapper


class MutatedPkg(wrapper):
    __slots__ = ("_overrides",)

    def __init__(self, pkg, overrides):
        """
        :param pkg: :obj:`pkgcore.package.metadata.package` to wrap
        :param overrides: is an attr -> instance mapping to substitute when
            the attr is requested
        """
        super().__init__(pkg)
        object.__setattr__(self, "_overrides", overrides)

    def __getattr__(self, attr):
        o = self._overrides.get(attr)
        if o is not None:
            return o
        return getattr(self._raw_pkg, attr)

    def __repr__(self):
        return '<%s pkg=%r overrides=%r @%#8x>' % (
            self.__class__.__name__, self._raw_pkg, tuple(self._overrides),
            id(self))

    def __str__(self):
        return '%s(%s, overrides=%s)' % \
            (self.__class__.__name__, self._raw_pkg, tuple(self._overrides))
