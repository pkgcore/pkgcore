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
        return f"<{self.__class__.__name__} pkg={self._raw_pkg!r} overrides={tuple(self._overrides)!r} @{id(self):#8x}>"

    def __str__(self):
        return f"{self.__class__.__name__}({self._raw_pkg}, overrides={tuple(self._overrides)})"
